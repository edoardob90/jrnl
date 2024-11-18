# Copyright © 2024 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import json
import textwrap
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.messages import MsgTextBase
from jrnl.output import print_msg
from jrnl.plugins.dayone_index import DayOneIndex
from jrnl.plugins.dayone_index import DayOneIndexMsg
from jrnl.plugins.util import localize
from jrnl.prompt import yesno

if TYPE_CHECKING:
    from jrnl.journals import Journal


class DayOneMsg(MsgTextBase):
    """Messages specific to Day One import functionality."""

    NoInputPath = "Day One JSON import requires an input file path"
    InvalidJSON = "Cannot parse Day One JSON: {error}"
    InvalidExport = "Invalid Day One export: {reason}"
    MediaNotFound = "Media file not found at {path}"
    MediaProcessed = "Successfully processed {count} media files from Day One export"
    ProcessingEntry = "Processing Day One entry {current} of {total}"
    Continue = "Do you want to continue importing entries from Day One?"


class DayOneJSONImporter:
    """Imports entries from Day One JSON export files.

    The importer handles:
    - Basic entry contents with titles and text
    - Media references (photos, PDFs, audio files)
    - Location data
    - Weather information
    - Device information
    - Starred/favorite status
    """

    names = ["dayone"]

    @staticmethod
    def _convert(entry: dict[str, Any], base_path: Path) -> str:
        """Convert a Day One entry to jrnl format.

        Args:
            entry: A Day One entry dict containing at least 'creationDate' and 'text'
            base_path: Path to the Day One export directory for resolving media paths

        Returns:
            A string containing the entry formatted for jrnl
        """
        # Convert creation date to local time (Day One uses UTC)
        date = datetime.fromisoformat(entry["creationDate"].replace("Z", "+00:00"))
        if tz := entry.get("timeZone"):
            tz = tz.replace("\\", "")
            date = localize(date, tz)
        date_str = f"[{date.strftime('%Y-%m-%d %H:%M:%S %p')}]"

        # Cleanup entry text from spurious escape sequences
        if text := entry.get("text"):
            text = text.replace("\\!", "!").replace("\\.", ".").replace("\\n", "\n")

        # Fetch tags (if any) and add them as the first line
        if tags := entry.get("tags"):
            tags = [(t[0].lower() + t[1:]).replace(" ", "") for t in tags]
            tags_str = " ".join(f"#{tag}" for tag in tags)
        else:
            tags_str = "#untagged"

        # Add star marker if entry is starred/favorite
        tags_str += " *\n" if entry.get("starred", False) else "\n"

        # Handle media references
        if text:
            if "photos" in entry:
                for photo in entry["photos"]:
                    moment_url = f"dayone-moment://{photo['identifier']}"
                    local_path = (
                        base_path / "photos" / f"{photo['md5']}.{photo['type']}"
                    )
                    text = text.replace(f"![]({moment_url})", f"![]({local_path})")

            if "pdfAttachments" in entry:
                for pdf in entry["pdfAttachments"]:
                    moment_url = f"dayone-moment:/pdfAttachment/{pdf['identifier']}"
                    local_path = base_path / "pdfs" / f"{pdf['md5']}.pdf"
                    text = text.replace(f"![]({moment_url})", f"![]({local_path})")

            if "audios" in entry:
                for audio in entry["audios"]:
                    moment_url = f"dayone-moment:/audio/{audio['identifier']}"
                    local_path = (
                        base_path / "audios" / f"{audio['md5']}.{audio['format']}"
                    )
                    text = text.replace(f"![]({moment_url})", f"![]({local_path})")

        # Add metadata lines (indented with 4 spaces)
        metadata_lines = []

        if "location" in entry:
            loc = entry["location"]

            place = [
                loc[key]
                for key in ("placeName", "localityName", "Country")
                if key in loc
            ]

            if place_str := ", ".join(place) if place else "":
                metadata_lines.append(f"Place:: {place_str}")

            metadata_lines.append(f"Location:: {loc['latitude']}, {loc['longitude']}")

        if "weather" in entry:
            w = entry["weather"]
            metadata_lines.append(
                f"Weather:: {w['conditionsDescription']}, "
                f"{w['temperatureCelsius']:.1f}°C, "
                f"{w['windSpeedKPH']:.1f} km/h"
            )

        if "creationDevice" in entry:
            metadata_lines.append(
                f"Device:: {entry['creationDevice']} ({entry['creationDeviceType']})"
            )

        # Construct final entry
        lines = [f"{date_str} {tags_str}"]

        if metadata_lines:
            metatada_str = textwrap.indent("\n".join(metadata_lines), prefix="    ")
            lines.append(metatada_str)

        if text:
            lines.extend(["", text.strip()])

        return "\n".join(lines)

    @staticmethod
    def import_(journal: "Journal", input: str | None = None) -> None:
        """Import entries from a Day One JSON export file.

        Args:
            journal: The journal to import entries into
            input: Path to the Day One JSON export file

        Raises:
            JrnlException: If the input path is invalid or the JSON cannot be parsed

        Returns:
            None. Prints a Message indicating the import results
        """
        if not input:
            raise JrnlException(Message(DayOneMsg.NoInputPath, MsgStyle.ERROR))

        input_path = Path(input)
        if not input_path.exists():
            raise JrnlException(
                Message(MsgText.DoesNotExist, MsgStyle.ERROR, {"name": str(input_path)})
            )

        try:
            with open(input_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise JrnlException(
                Message(DayOneMsg.InvalidJSON, MsgStyle.ERROR, {"error": str(e)})
            )

        if "entries" not in data:
            raise JrnlException(
                Message(
                    DayOneMsg.InvalidExport,
                    MsgStyle.ERROR,
                    {"reason": "no entries found"},
                )
            )

        # Verify media files exist
        media_types = {"photos": "photos", "pdfAttachments": "pdfs", "audios": "audios"}
        media_count = 0
        for entry in data.get("entries", []):
            for media_type, media_dir in media_types.items():
                for media in entry.get(media_type, []):
                    ext = media.get("type", "") or media.get("format", "")
                    # Inconsistent media type and ext if media is an audio file
                    ext = "m4a" if ext == "aac" else ext
                    media_path = input_path.parent / media_dir / f"{media['md5']}.{ext}"
                    if not media_path.exists():
                        print_msg(
                            Message(
                                DayOneMsg.MediaNotFound,
                                MsgStyle.WARNING,
                                {"path": str(media_path)},
                            )
                        )
                    else:
                        media_count += 1

        if media_count > 0:
            print_msg(
                Message(
                    DayOneMsg.MediaProcessed,
                    MsgStyle.NORMAL,
                    {"count": media_count},
                )
            )

        # Setup index for resolving links
        try:
            index = DayOneIndex()
        except KeyboardInterrupt:
            print_msg(Message(MsgText.ImportAborted, MsgStyle.WARNING))
            return None
        else:
            # Check if the index is up-to-date
            if (
                index.is_usable
                and index.last_modified.timestamp() < input_path.stat().st_ctime
            ):
                print_msg(Message(DayOneIndexMsg.IndexOutdated, MsgStyle.WARNING))
                proceed = yesno(Message(DayOneMsg.Continue), default=False)
                if not proceed:
                    print_msg(Message(MsgText.ImportAborted, MsgStyle.WARNING))
                    return None

        # Process entries with status updates
        old_cnt = len(journal.entries)
        total_entries = len(data["entries"])
        entries_text = []
        for i, entry in enumerate(data["entries"], 1):
            print_msg(
                Message(
                    DayOneMsg.ProcessingEntry,
                    MsgStyle.NORMAL,
                    {"current": i, "total": total_entries},
                )
            )

            # Convert entry
            entry_text = DayOneJSONImporter._convert(entry, input_path.parent)

            # Resolve any links in the entry
            if entry_text:
                entry_text = index.resolve_links(entry_text)
                print(entry_text)
                # Add entry to journal
                entries_text.append(entry_text)

        # Import all entries
        journal.import_("\n\n".join(entries_text))
        journal.write()

        # Return import summary
        new_cnt = len(journal.entries)
        print_msg(
            Message(
                MsgText.ImportSummary,
                MsgStyle.NORMAL,
                {"count": new_cnt - old_cnt, "journal_name": journal.name},
            )
        )

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict
from typing import Optional
from urllib.parse import unquote

from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgTextBase
from jrnl.output import print_msg
from jrnl.plugins.util import localize
from jrnl.prompt import yesno


def extract_journal_name(export_path: Path) -> str:
    """
    Extract original journal name from Day One export filename.

    Args:
        export_path: Path to the Day One JSON export file

    Returns:
        The original journal name with proper Unicode decoding

    Example:
        >>> extract_journal_name(Path("🧪 Test 2.json"))
        '🧪 Test 2'
        >>> extract_journal_name(Path("%F0%9F%A7%AA Test 2.json"))
        '🧪 Test 2'
    """
    return unquote(export_path.stem)


class DayOneIndexMsg(MsgTextBase):
    """Messages specific to Day One index functionality."""

    IndexFileMissing = "Creating a Day One index requires an input file"
    IndexFileNotFound = "Day One index file {path} does not exist"
    IndexFileMalformed = "Cannot parse Day One index file: {error}"
    IndexLoadError = "Cannot load Day One index: {error}"
    IndexNotFound = (
        "No Day One index found. Run 'jrnl --index' first to enable link resolution"
    )
    IndexCreated = "Day One index created from {count} entries"
    IndexUpdated = "Day One index updated ({count} entries)"
    IndexUpToDate = "Day One index is up-to-date"
    IndexClearConfirm = "Do you want to clear the Day One index?"
    IndexCleared = "Day One index cleared"
    IndexNotUsable = (
        "Cannot resolve Day One links: index not found or empty. "
        "Run 'jrnl --index --file path/to/dayone.json' first"
    )
    InvalidJournalName = "Journal name '{name}' is not a valid UTF-8 string"


class IndexMode(Enum):
    """Mode for Day One index creation"""

    USE = 0
    BUILD = 1


@dataclass(eq=False, frozen=True)
class IndexedEntry:
    """Entry stored in a Day One index file"""

    uuid: str
    date: datetime
    journal_name: str
    original_journal_name: str  # Original Day One journal name

    def __post_init__(self):
        try:
            self.original_journal_name.encode("utf-8").decode("utf-8")
        except UnicodeError:
            raise JrnlException(
                Message(
                    DayOneIndexMsg.InvalidJournalName,
                    MsgStyle.ERROR,
                    {"name": self.original_journal_name},
                )
            )

    def __eq__(self, other: object, /) -> bool:
        if not isinstance(other, IndexedEntry):
            return NotImplemented
        return self.uuid == other.uuid

    def __hash__(self) -> int:
        return hash(self.uuid)


class DayOneIndex:
    """Persistent index of Day One entry UUIDs across multiple exports and journals"""

    def __init__(self, mode: IndexMode = IndexMode.USE):
        from jrnl.path import get_config_path

        config_dir = Path(get_config_path()).parent
        self.index_file = config_dir / "dayone_index.json"
        self.entries: Dict[str, IndexedEntry] = {}
        self.last_modified: datetime = datetime.min
        self.mode = mode
        self._load_index()

    @property
    def is_usable(self) -> bool:
        """Check if the index is usable"""
        return self.index_file.exists() and len(self.entries) > 0

    def __getitem__(self, uuid: str) -> Optional[IndexedEntry]:
        """Look up an entry by UUID"""
        if not self.is_usable and self.mode == IndexMode.USE:
            print_msg(Message(DayOneIndexMsg.IndexNotUsable, MsgStyle.WARNING))
            return None
        return self.entries.get(uuid)

    def __len__(self) -> int:
        return len(self.entries)

    def _load_index(self) -> None:
        """Load existing index if it exists"""
        if not self.index_file.exists():
            if self.mode == IndexMode.USE:
                print_msg(Message(DayOneIndexMsg.IndexNotFound, MsgStyle.WARNING))
            return

        try:
            with self.index_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            self.entries = {
                uuid: IndexedEntry(
                    uuid=uuid,
                    date=datetime.fromisoformat(entry["date"]),
                    journal_name=entry["journal_name"],
                    original_journal_name=entry["orignal_journal_name"],
                )
                for uuid, entry in data["entries"].items()
            }
        except KeyError as e:
            raise JrnlException(
                Message(
                    DayOneIndexMsg.IndexFileMalformed,
                    MsgStyle.ERROR,
                    {"error": str(e)},
                )
            ) from e
        except Exception as e:
            raise JrnlException(
                Message(
                    DayOneIndexMsg.IndexLoadError,
                    MsgStyle.ERROR,
                    {"error": str(e)},
                )
            ) from e

    def _save_index(self) -> None:
        """Save index to disk"""
        data = {
            "last_modified": self.last_modified.isoformat(),
            "entries": {
                uuid: {
                    "date": entry.date.isoformat(),
                    "journal_name": entry.journal_name,
                    "orignal_journal_name": entry.original_journal_name,
                }
                for uuid, entry in self.entries.items()
            },
        }

        with self.index_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def clear(self) -> None:
        """Clear the index"""
        clear = yesno(Message(DayOneIndexMsg.IndexClearConfirm), default=False)
        if clear:
            self.last_modified = datetime.now()
            self.entries = {}
            self._save_index()

    def add_entries(
        self, entries: list[dict], journal_name: str, export_journal_source: Path
    ) -> None:
        """
        Add entries from a Day One export to the index

        Args:
            entries: List of Day One entry dictionaries
            journal_name: Unique name of the journal these entries belong to
            export_source: Path to the Day One JSON export file
        """
        orignal_journal_name = extract_journal_name(export_journal_source)

        entries_count_before = len(self)

        for entry in entries:
            uuid = entry.get("uuid")
            if not uuid or uuid in self.entries:
                continue

            date = datetime.fromisoformat(entry["creationDate"].replace("Z", "+00:00"))
            if tz := entry.get("timeZone"):
                tz = tz.replace("\\", "")
                date = localize(date, tz)

            self.entries[uuid] = IndexedEntry(
                uuid=uuid,
                date=date,
                journal_name=journal_name,
                original_journal_name=orignal_journal_name,
            )

        entries_count_after = len(self)

        is_created = entries_count_before == 0
        is_updated = entries_count_after > entries_count_before

        if is_created or is_updated:
            self.last_modified = datetime.now()
            self._save_index()

            if is_created:
                msg = DayOneIndexMsg.IndexCreated
                count = entries_count_after
            else:
                msg = DayOneIndexMsg.IndexUpdated
                count = entries_count_after - entries_count_before

            print_msg(Message(msg, MsgStyle.NORMAL, {"count": count}))
        else:
            print_msg(Message(DayOneIndexMsg.IndexUpToDate, MsgStyle.NORMAL))

    def resolve_links(self, text: str) -> str:
        """Resolve Day One links in the given text"""
        link_re = re.compile(r"\[([^\]]+)\]\(dayone2://view\?Id=([a-zA-Z0-9-]+)\)")

        def replace_link(match: re.Match) -> str:
            link_text, entry_uuid = match.groups()

            if not (target := self[entry_uuid]):
                return match.group(0)

            return f"[[{target.journal_name}/{target.date:%Y/%m/%d}|{link_text}]]"

        return link_re.sub(replace_link, text)

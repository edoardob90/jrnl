import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict
from typing import Optional

from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgTextBase
from jrnl.output import print_msg
from jrnl.plugins.util import localize


class DayOneIndexMsg(MsgTextBase):
    """Messages specific to Day One index functionality."""

    IndexFileMissing = "Creating a Day One index requires an input file"
    IndexFileNotFound = "Day One index file {path} does not exist"
    IndexNotFound = (
        "No Day One index found. Run 'jrnl --index' first to enable link resolution"
    )
    IndexCreated = "Day One index created from {count} entries"
    IndexUpdated = "Day One index updated ({count} entries)"
    IndexCleared = "Day One index cleared"
    IndexNotUsable = (
        "Cannot resolve Day One links: index not found or empty. "
        "Run 'jrnl --index --file path/to/dayone.json' first"
    )


class IndexMode(Enum):
    """Mode for Day One index creation"""

    USE = 0
    BUILD = 1


@dataclass(eq=False, frozen=True)
class IndexedEntry:
    """Information about a Day One entry needed for link resolution"""

    uuid: str
    date: datetime
    journal_name: str
    export_source: str  # Original Day One JSON file

    def __eq__(self, other: object, /) -> bool:
        if not isinstance(other, IndexedEntry):
            return NotImplemented
        return self.uuid == other.uuid

    def __hash__(self) -> int:
        return hash(self.uuid)


class DayOneIndex:
    """Maintains a persistent index of Day One entry UUIDs across multiple exports"""

    def __init__(self, mode: IndexMode = IndexMode.USE):
        from jrnl.path import get_config_path

        config_dir = Path(get_config_path()).parent
        self.index_file = config_dir / "dayone_index.json"
        self.entries: Dict[str, IndexedEntry] = {}
        self.mode = mode
        self._load_index()

    @property
    def is_usable(self) -> bool:
        """Check if the index is usable"""
        return self.index_file.exists() and len(self.entries) > 0

    def _load_index(self) -> None:
        """Load existing index if it exists"""
        if not self.index_file.exists():
            if self.mode == IndexMode.USE:
                print_msg(Message(DayOneIndexMsg.IndexNotFound, MsgStyle.WARNING))
            return

        try:
            with open(self.index_file, "r") as f:
                data = json.load(f)

            self.entries = {
                uuid: IndexedEntry(
                    uuid=uuid,
                    date=datetime.fromisoformat(entry["date"]),
                    journal_name=entry["journal_name"],
                    export_source=entry["export_source"],
                )
                for uuid, entry in data.items()
            }
        except Exception:
            # TODO: add some warning message that something went wrong
            self.entries = {}

    def _save_index(self) -> None:
        """Save index to disk"""
        data = {
            uuid: {
                "date": entry.date.isoformat(),
                "journal_name": entry.journal_name,
                "export_source": entry.export_source,
            }
            for uuid, entry in self.entries.items()
        }

        with open(self.index_file, "w") as f:
            json.dump(data, f, indent=2)

    def clear(self) -> None:
        """Clear the index"""
        self.entries = {}
        self._save_index()

    def add_entries(
        self, entries: list[dict], journal_name: str, export_source: Path
    ) -> None:
        """
        Add entries from a Day One export to the index

        Args:
            entries: List of Day One entry dictionaries
            journal_name: Unique name of the journal these entries belong to
            export_source: Path to the Day One JSON export file
        """
        new_entries = False
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
                export_source=str(export_source),
            )

            new_entries = True

        if new_entries:
            self._save_index()

    def __getitem__(self, uuid: str) -> Optional[IndexedEntry]:
        """Look up an entry by UUID"""
        if not self.is_usable and self.mode == IndexMode.USE:
            print_msg(Message(DayOneIndexMsg.IndexNotUsable, MsgStyle.WARNING))
            return None
        return self.entries.get(uuid)

    def __len__(self) -> int:
        return len(self.entries)

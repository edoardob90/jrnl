# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html
from enum import Enum


class MsgTextBase(Enum):
    """Base class for jrnl messages."""

    def __str__(self) -> str:
        return self.value

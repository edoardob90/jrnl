# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

from typing import TYPE_CHECKING
from typing import Mapping
from typing import NamedTuple

from jrnl.messages.MsgStyle import MsgStyle

if TYPE_CHECKING:
    from jrnl.messages.MsgTextBase import MsgTextBase


class Message(NamedTuple):
    text: "MsgTextBase"
    style: MsgStyle = MsgStyle.NORMAL
    params: Mapping = {}

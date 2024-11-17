# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html
from typing import TypeAlias

from jrnl.messages import Message as _Message
from jrnl.messages import MsgStyle as _MsgStyle
from jrnl.messages import MsgText as _MsgText
from jrnl.messages import MsgTextBase as _MsgTextBase

Message: TypeAlias = _Message.Message
MsgStyle: TypeAlias = _MsgStyle.MsgStyle
MsgText: TypeAlias = _MsgText.MsgText
MsgTextBase: TypeAlias = _MsgTextBase.MsgTextBase

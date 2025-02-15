# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

"""
Functions in this file are standalone commands. All standalone commands are split into
two categories depending on whether they require the config to be loaded to be able to
run.

1. "preconfig" commands don't require the config at all, and can be run before the
   config has been loaded.
2. "postconfig" commands require to config to have already been loaded, parsed, and
   scoped before they can be run.

Also, please note that all (non-builtin) imports should be scoped to each function to
avoid any possible overhead for these standalone commands.
"""

import argparse
import json
import logging
import platform
import sys
from pathlib import Path

from jrnl.config import cmd_requires_valid_journal_name
from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.output import print_msg
from jrnl.plugins.dayone_index import DayOneIndex
from jrnl.plugins.dayone_index import DayOneIndexMsg
from jrnl.plugins.dayone_index import IndexMode
from jrnl.plugins.dayone_json_importer import DayOneMsg


def preconfig_diagnostic(_) -> None:
    from jrnl import __title__
    from jrnl import __version__

    print(
        f"{__title__}: {__version__}\n"
        f"Python: {sys.version}\n"
        f"OS: {platform.system()} {platform.release()}"
    )


def preconfig_version(_) -> None:
    import textwrap

    from jrnl import __title__
    from jrnl import __version__

    output = f"""
    {__title__} {__version__}

    Copyright © 2012-2023 jrnl contributors

    This is free software, and you are welcome to redistribute it under certain
    conditions; for details, see: https://www.gnu.org/licenses/gpl-3.0.html
    """

    output = textwrap.dedent(output).strip()

    print(output)


def postconfig_list(args: argparse.Namespace, config: dict, **_) -> int:
    from jrnl.output import list_journals

    print(list_journals(config, args.export))

    return 0


@cmd_requires_valid_journal_name
def postconfig_import(args: argparse.Namespace, config: dict, **_) -> int:
    from jrnl.journals import open_journal
    from jrnl.plugins import get_importer

    # Requires opening the journal
    journal = open_journal(args.journal_name, config)

    format = args.export if args.export else "jrnl"
    get_importer(format).import_(journal, args.filename)

    return 0


@cmd_requires_valid_journal_name
def postconfig_encrypt(
    args: argparse.Namespace, config: dict, original_config: dict
) -> int:
    """
    Encrypt a journal in place, or optionally to a new file
    """
    from jrnl.config import update_config
    from jrnl.install import save_config
    from jrnl.journals import open_journal

    # Open the journal
    journal = open_journal(args.journal_name, config)

    if hasattr(journal, "can_be_encrypted") and not journal.can_be_encrypted:
        raise JrnlException(
            Message(
                MsgText.CannotEncryptJournalType,
                MsgStyle.ERROR,
                {
                    "journal_name": args.journal_name,
                    "journal_type": journal.__class__.__name__,
                },
            )
        )

    # If journal is encrypted, create new password
    logging.debug("Clearing encryption method...")

    if journal.config["encrypt"] is True:
        logging.debug("Journal already encrypted. Re-encrypting...")
        print(f"Journal {journal.name} is already encrypted. Create a new password.")
        journal.encryption_method.clear()
    else:
        journal.config["encrypt"] = True
        journal.encryption_method = None

    journal.write(args.filename)

    print_msg(
        Message(
            MsgText.JournalEncryptedTo,
            MsgStyle.NORMAL,
            {"path": args.filename or journal.config["journal"]},
        )
    )

    # Update the config, if we encrypted in place
    if not args.filename:
        update_config(
            original_config, {"encrypt": True}, args.journal_name, force_local=True
        )
        save_config(original_config)

    return 0


@cmd_requires_valid_journal_name
def postconfig_decrypt(
    args: argparse.Namespace, config: dict, original_config: dict
) -> int:
    """Decrypts to file. If filename is not set, we encrypt the journal file itself."""
    from jrnl.config import update_config
    from jrnl.install import save_config
    from jrnl.journals import open_journal

    journal = open_journal(args.journal_name, config)

    logging.debug("Clearing encryption method...")
    journal.config["encrypt"] = False
    journal.encryption_method = None

    journal.write(args.filename)
    print_msg(
        Message(
            MsgText.JournalDecryptedTo,
            MsgStyle.NORMAL,
            {"path": args.filename or journal.config["journal"]},
        )
    )

    # Update the config, if we decrypted in place
    if not args.filename:
        update_config(
            original_config, {"encrypt": False}, args.journal_name, force_local=True
        )
        save_config(original_config)

    return 0


@cmd_requires_valid_journal_name
def postconfig_index(args: argparse.Namespace, config: dict, **kwargs) -> int:
    """
    Standalone command to build/update the Day One index
    """
    # Initialize the index
    index = DayOneIndex(mode=IndexMode.BUILD)

    # Check if --clear flag is set
    if args.clear:
        index.clear()
        print_msg(Message(DayOneIndexMsg.IndexCleared, MsgStyle.NORMAL))
        return 0

    if not args.filename:
        raise JrnlException(
            Message(
                DayOneIndexMsg.IndexFileMissing,
                MsgStyle.ERROR,
            )
        )

    # Load and process Day One JSON file
    input_path = Path(args.filename)
    if not input_path.exists():
        raise JrnlException(
            Message(
                DayOneIndexMsg.IndexFileNotFound,
                MsgStyle.ERROR,
                {"path": input_path},
            )
        )

    with open(input_path, "r") as f:
        data = json.load(f)

    if "entries" not in data:
        raise JrnlException(
            Message(
                DayOneMsg.InvalidExport,
                MsgStyle.ERROR,
                {"reason": "no.entries found"},
            )
        )

    # Update the index
    index.add_entries(data["entries"], args.journal_name, input_path)

    msg = (
        DayOneIndexMsg.IndexCreated
        if len(index) == len(data["entries"])
        else DayOneIndexMsg.IndexUpdated
    )
    print_msg(Message(msg, MsgStyle.NORMAL, {"count": len(index.entries)}))

    return 0

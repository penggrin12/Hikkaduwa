"""Processes incoming events and dispatches them to appropriate handlers"""

#    Friendly Telegram (telegram userbot)
#    Copyright (C) 2018-2022 The Authors

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import collections
import contextlib
import copy
import inspect
import logging
import re
import sys
import traceback
import typing

import pyrogram
import pyrogram.errors
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from . import features, main, utils

if typing.TYPE_CHECKING:
    from .client import HikkaClient
    from .database import Database
    from .loader import Modules

logger = logging.getLogger(__name__)

# Keys for layout switch
ru_keys = 'ёйцукенгшщзхъфывапролджэячсмитьбю.Ё"№;%:?ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭ/ЯЧСМИТЬБЮ,'
en_keys = "`qwertyuiop[]asdfghjkl;'zxcvbnm,./~@#$%^&QWERTYUIOP{}ASDFGHJKL:\"|ZXCVBNM<>?"
ALL_TAGS = [
    "no_commands",
    "only_commands",
    "out",
    "in",
    "only_messages",
    "editable",
    "no_media",
    "only_media",
    "only_photos",
    "only_videos",
    "only_audios",
    "only_docs",
    "only_stickers",
    "only_inline",
    "only_channels",
    "only_groups",
    "only_pm",
    "no_pm",
    "no_channels",
    "no_groups",
    "no_inline",
    "no_stickers",
    "no_docs",
    "no_audios",
    "no_videos",
    "no_photos",
    "no_forwards",
    "no_reply",
    "no_mention",
    "mention",
    "only_reply",
    "only_forwards",
    "startswith",
    "endswith",
    "contains",
    "regex",
    "filter",
    "from_id",
    "chat_id",
    "thumb_url",
    "alias",
    "aliases",
]


def _decrement_ratelimit(delay, data, key, severity) -> None:
    def inner():
        data[key] = max(0, data[key] - severity)

    asyncio.get_event_loop().call_later(delay, inner)


class CommandDispatcher:
    def __init__(
        self,
        modules: "Modules",
        client: "HikkaClient",
        db: "Database",
    ):
        self._modules: "Modules" = modules
        self._client: "HikkaClient" = client
        self.client: "HikkaClient" = client
        self._db: "Database" = db

        self._ratelimit_storage_user = collections.defaultdict(int)
        self._ratelimit_storage_chat = collections.defaultdict(int)
        self._ratelimit_max_user = db.get(__name__, "ratelimit_max_user", 30)
        self._ratelimit_max_chat = db.get(__name__, "ratelimit_max_chat", 100)

        self._me: int = self._client.hikka_me.id
        self._cached_usernames: list[str] = [
            (
                self._client.hikka_me.username.lower()
                if self._client.hikka_me.username
                else str(self._client.hikka_me.id)
            )
        ]

        self._cached_usernames.extend(
            getattr(self._client.hikka_me, "usernames", None) or []
        )

        self.raw_handlers = []

    async def _handle_ratelimit(self, message: Message, func: typing.Callable) -> bool:
        func = getattr(func, "__func__", func)
        ret = True
        chat = self._ratelimit_storage_chat[message.chat.id]

        if message.from_user:
            user = self._ratelimit_storage_user[message.from_user.id]
            severity = (5 if getattr(func, "ratelimit", False) else 2) * (
                (user + chat) // 30 + 1
            )
            user += severity
            self._ratelimit_storage_user[message.from_user.id] = user
            if user > self._ratelimit_max_user:
                ret = False
            else:
                self._ratelimit_storage_chat[message.chat.id] = chat

            _decrement_ratelimit(
                self._ratelimit_max_user * severity,
                self._ratelimit_storage_user,
                message.from_user.id,
                severity,
            )
        else:
            severity = (5 if getattr(func, "ratelimit", False) else 2) * (
                chat // 15 + 1
            )

        chat += severity

        if chat > self._ratelimit_max_chat:
            ret = False

        _decrement_ratelimit(
            self._ratelimit_max_chat * severity,
            self._ratelimit_storage_chat,
            message.chat.id,
            severity,
        )

        return ret

    async def _handle_command(
        self,
        message: pyrogram.types.Message,
        watcher: bool = False,
    ) -> (
        tuple[pyrogram.types.Message, str, str, typing.Callable] | typing.Literal[False]
    ):
        if not message.text:
            return False

        prefix: str = typing.cast(
            str, self._db.get(main.__name__, "command_prefix", ".")
        )
        if not message.text.startswith(prefix):
            return False

        text: str = utils.censor(message.text)

        if (
            message.sticker or message.dice or message.audio or message.via_bot
            # or message.reactions
        ):
            return False

        if len(text) == len(prefix):
            return False  # Message is just the prefix

        if (not message.from_user) or message.from_user.id != self._me:
            return False

        command = message.text[1:].strip().split(maxsplit=1)[0]

        txt, func = self._modules.dispatch(command)

        if not func or not await self._handle_ratelimit(message, func):
            return False

        if message.chat.type == pyrogram.enums.ChatType.CHANNEL and message.edit_date:
            if features.WORK_IN_CHANNELS:
                async for event in self._client.iter_admin_log(
                    utils.get_chat_id(message),
                    limit=10,
                    edit=True,
                ):
                    if event.action.prev_message.id == message.id:
                        if event.user_id != self._client.tg_id:
                            logger.debug("Ignoring edit in channel")
                            return False

                        break

        if (
            message.chat.type == pyrogram.enums.ChatType.SUPERGROUP
            and message.chat.title
            and message.chat.title.startswith("hikka-")
            and message.chat.title != "hikka-logs"
        ):
            if not watcher:
                logger.warning("Ignoring message in datachat \\ logging chat")
            return False

        message.text = prefix + txt + message.text[len(prefix + command) :]

        if await self._handle_tags(message, func):
            return False

        return message, prefix, txt, func

    async def handle_raw(self, _, update: pyrogram.raw.base.Update, __, ___):
        """Handle raw events."""
        for handler in self.raw_handlers:
            if isinstance(update, tuple(handler.updates)):
                try:
                    await handler(update)
                except Exception as e:
                    logger.exception("Error in raw handler %s: %s", handler.id, e)

    async def handle_command(self, _, message: pyrogram.types.Message):
        """Handle all commands"""
        message = await self._handle_command(message)
        if not message:
            return

        message, _, _, func = message

        asyncio.ensure_future(
            self.future_dispatcher(
                func,
                message,
                self.command_exc,
            )
        )

    async def command_exc(self, _, message: Message):
        """Handle command exceptions."""
        exc = sys.exc_info()[1]
        logger.exception("Command failed", extra={"stack": inspect.stack()})
        if isinstance(exc, pyrogram.errors.RPCError):
            if isinstance(exc, FloodWait):
                hours = exc.value // 3600
                minutes = (exc.value % 3600) // 60
                seconds = exc.value % 60
                hours = f"{hours} hours, " if hours else ""
                minutes = f"{minutes} minutes, " if minutes else ""
                seconds = f"{seconds} seconds" if seconds else ""
                fw_time = f"{hours}{minutes}{seconds}"
                txt = (
                    # FIXME: translations no more
                    self._client.loader.lookup("translations")
                    .strings("fw_error")
                    .format(utils.escape_html(message.text or ""), fw_time, "?")
                )
            else:
                txt = (
                    "🚫 <b>Call"
                    f" </b><code>{utils.escape_html(message.text or '')}</code><b> failed"
                    " due to RPC (Telegram) error:</b>"
                    f" <code>{utils.escape_html(str(exc))}</code>"
                )
        else:
            if not self._db.get(main.__name__, "inlinelogs", True):
                txt = (
                    "🚫<b> Call</b>"
                    f" <code>{utils.escape_html(message.text or '')}</code><b>"
                    " failed!</b>"
                )
            else:
                exc = "\n".join(traceback.format_exc().splitlines()[1:])
                txt = (
                    "🚫<b> Call</b>"
                    f" <code>{utils.escape_html(message.text or '')}</code><b>"
                    " failed!</b>\n\n<b>🧾"
                    f" Logs:</b>\n<code>{utils.escape_html(exc)}</code>"
                )

        with contextlib.suppress(Exception):
            await (message.edit if message.outgoing else message.reply)(txt)

    async def watcher_exc(self, *_):
        logger.exception("Error running watcher", extra={"stack": inspect.stack()})

    async def _handle_tags(
        self,
        message: Message,
        func: typing.Callable,
    ) -> bool:
        return bool(await self._handle_tags_ext(message, func))

    async def _handle_tags_ext(
        self,
        message: Message,
        func: typing.Callable,
    ) -> str:
        """
        Handle tags.
        :param event: The event to handle.
        :param func: The function to handle.
        :return: The reason for the tag to fail.
        """
        m = message

        reverse_mapping = {
            "out": lambda: getattr(m, "out", True),
            "in": lambda: not getattr(m, "out", True),
            "only_messages": lambda: isinstance(m, Message),
            "editable": (
                lambda: (
                    not getattr(m, "out", False)
                    and not getattr(m, "fwd_from", False)
                    and not getattr(m, "sticker", False)
                    and not getattr(m, "via_bot_id", False)
                )
            ),
            "no_media": lambda: (
                not isinstance(m, Message) or not getattr(m, "media", False)
            ),
            "only_media": lambda: isinstance(m, Message) and getattr(m, "media", False),
            "only_photos": lambda: utils.mime_type(m).startswith("image/"),
            "only_videos": lambda: utils.mime_type(m).startswith("video/"),
            "only_audios": lambda: utils.mime_type(m).startswith("audio/"),
            "only_stickers": lambda: getattr(m, "sticker", False),
            "only_docs": lambda: getattr(m, "document", False),
            "only_inline": lambda: getattr(m, "via_bot_id", False),
            "only_channels": lambda: (
                getattr(m, "is_channel", False) and not getattr(m, "is_group", False)
            ),
            "no_channels": lambda: not getattr(m, "is_channel", False),
            "no_groups": (
                lambda: (
                    not getattr(m, "is_group", False)
                    or getattr(m, "private", False)
                    or getattr(m, "is_channel", False)
                )
            ),
            "only_groups": (
                lambda: (
                    getattr(m, "is_group", False)
                    or not getattr(m, "private", False)
                    and not getattr(m, "is_channel", False)
                )
            ),
            "no_pm": lambda: not getattr(m, "private", False),
            "only_pm": lambda: getattr(m, "private", False),
            "no_inline": lambda: not getattr(m, "via_bot_id", False),
            "no_stickers": lambda: not getattr(m, "sticker", False),
            "no_docs": lambda: not getattr(m, "document", False),
            "no_audios": lambda: not utils.mime_type(m).startswith("audio/"),
            "no_videos": lambda: not utils.mime_type(m).startswith("video/"),
            "no_photos": lambda: not utils.mime_type(m).startswith("image/"),
            "no_forwards": lambda: not getattr(m, "fwd_from", False),
            "no_reply": lambda: not getattr(m, "reply_to_msg_id", False),
            "only_forwards": lambda: getattr(m, "fwd_from", False),
            "only_reply": lambda: getattr(m, "reply_to_msg_id", False),
            "mention": lambda: getattr(m, "mentioned", False),
            "no_mention": lambda: not getattr(m, "mentioned", False),
            "startswith": lambda: (
                isinstance(m, Message) and m.raw_text.startswith(func.startswith)
            ),
            "endswith": lambda: (
                isinstance(m, Message) and m.raw_text.endswith(func.endswith)
            ),
            "contains": lambda: isinstance(m, Message) and func.contains in m.raw_text,
            "filter": lambda: callable(func.filter) and func.filter(m),
            "from_id": lambda: getattr(m, "sender_id", None) == func.from_id,
            "chat_id": lambda: (
                utils.get_chat_id(m)
                == (
                    func.chat_id
                    if not str(func.chat_id).startswith("-100")
                    else int(str(func.chat_id)[4:])
                )
            ),
            "regex": lambda: (
                isinstance(m, Message) and re.search(func.regex, m.raw_text)
            ),
        }

        return (
            "no_commands"
            if getattr(func, "no_commands", False)
            and await self._handle_command(message, watcher=True)
            else (
                "only_commands"
                if getattr(func, "only_commands", False)
                and not await self._handle_command(message, watcher=True)
                else next(
                    (
                        tag
                        for tag in ALL_TAGS
                        if getattr(func, tag, False)
                        and tag in reverse_mapping
                        and not reverse_mapping[tag]()
                    ),
                    None,
                )
            )
        )

    async def handle_incoming(self, _, message: pyrogram.types.Message):
        """Handle all incoming messages"""
        message = utils.censor(message)

        blacklist_chats = self._db.get(main.__name__, "blacklist_chats", [])
        whitelist_chats = self._db.get(main.__name__, "whitelist_chats", [])
        whitelist_modules = self._db.get(main.__name__, "whitelist_modules", [])

        if utils.get_chat_id(message) in blacklist_chats or (
            whitelist_chats and utils.get_chat_id(message) not in whitelist_chats
        ):
            logger.debug("Message is blacklisted")
            return

        for func in self._modules.watchers:
            bl = typing.cast(dict, self._db.get(main.__name__, "disabled_watchers", {}))
            modname = str(func.__self__.__class__.strings["name"])

            if (
                modname in bl
                and isinstance(message, Message)
                and (
                    "*" in bl[modname]
                    or utils.get_chat_id(message) in bl[modname]
                    or "only_chats" in bl[modname]
                    and message.is_private
                    or "only_pm" in bl[modname]
                    and not message.is_private
                    or "out" in bl[modname]
                    and not message.out
                    or "in" in bl[modname]
                    and message.out
                )
                or f"{str(utils.get_chat_id(message))}.{func.__self__.__module__}"
                in blacklist_chats
                or whitelist_modules
                and f"{str(utils.get_chat_id(message))}.{func.__self__.__module__}"
                not in whitelist_modules
                or await self._handle_tags(message, func)
            ):
                logger.debug(
                    "Ignored watcher of module %s because of %s",
                    modname,
                    await self._handle_tags_ext(message, func),
                )
                continue

            # Avoid weird AttributeErrors in weird dochub modules by settings placeholder
            # of attributes
            for placeholder in {"text", "raw_text", "out"}:
                try:
                    if not hasattr(message, placeholder):
                        setattr(message, placeholder, "")
                except UnicodeDecodeError:
                    pass

            # Run watcher via ensure_future so in case user has a lot
            # of watchers with long actions, they can run simultaneously
            asyncio.ensure_future(
                self.future_dispatcher(
                    func,
                    message,
                    self.watcher_exc,
                )
            )

    async def future_dispatcher(
        self,
        func: typing.Callable,
        message: pyrogram.types.Message,
        exception_handler: typing.Callable,
        *args,
    ):
        # Will be used to determine, which client caused logging messages
        # parsed via inspect.stack()
        _hikka_client_id_logging_tag = copy.copy(self.client.tg_id)  # noqa: F841
        try:
            await func(message)
        except Exception as e:
            await exception_handler(e, message, *args)

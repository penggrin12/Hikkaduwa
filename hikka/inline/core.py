"""Inline buttons, galleries and other Telegram-Bot-API stuff"""

# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import contextlib
import logging
import time
import typing

import pyrogram.errors
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError, TelegramUnauthorizedError
from pyrogram.raw.types.messages import BotResults
from pyrogram.types import Message

from .. import utils
from ..translations import Translator
from .bot_pm import BotPM
from .events import Events
from .form import Form
from .gallery import Gallery
from .list import List
from .query_gallery import QueryGallery
from .token_obtainment import TokenObtainment
from .utils import Utils

if typing.TYPE_CHECKING:
    from ..client import HikkaClient
    from ..database import Database
    from ..loader import Modules

logger = logging.getLogger(__name__)


class InlineManager(
    Utils,
    Events,
    TokenObtainment,
    Form,
    Gallery,
    QueryGallery,
    List,
    BotPM,
):
    """
    Inline buttons, galleries and other Telegram-Bot-API stuff
    :param client: Telegram client
    :param db: Database instance
    :param allmodules: All modules
    """

    def __init__(
        self,
        client: "HikkaClient",
        db: "Database",
        allmodules: "Modules",  # type: ignore  # noqa: F821
    ):
        """Initialize InlineManager to create forms"""
        self._client = client
        self._db = db
        self._allmodules = allmodules
        self.allmodules: "Modules" = allmodules
        self.translator: Translator = allmodules.translator

        self._units: dict[str, dict] = {}
        self._custom_map: dict[str, typing.Callable] = {}
        self.fsm: dict[str, str] = {}
        self._error_events: dict[str, asyncio.Event] = {}

        self._markup_ttl = 60 * 60 * 24
        self.init_complete = False

        self._token: str | None = str(db.get("hikka.inline", "bot_token", False))

        self._me: int = None
        self._name: str = None
        self._dp: Dispatcher = None
        self._task: asyncio.Future = None
        self._cleaner_task: asyncio.Future = None
        self.bot: Bot = None
        self.bot_id: int = None
        self.bot_username: str = None

    async def _cleaner(self) -> typing.NoReturn:
        """Cleans outdated inline units"""
        while True:
            for unit_id, unit in self._units.copy().items():
                if (unit.get("ttl") or (time.time() + self._markup_ttl)) < time.time():
                    del self._units[unit_id]

            await asyncio.sleep(5)

    async def register_manager(
        self,
        after_break: bool = False,
        ignore_token_checks: bool = False,
    ) -> None:
        """
        Register manager
        :param after_break: Loop marker
        :param ignore_token_checks: If `True`, will not check for token
        :type after_break: bool
        :type ignore_token_checks: bool
        :return: None
        :rtype: None
        """
        self._me = self._client._tg_id
        self._name = utils.get_display_name(self._client.hikka_me)

        if not ignore_token_checks:
            is_token_asserted = await self._assert_token()
            if not is_token_asserted:
                self.init_complete = False
                return

        self.init_complete = True

        self.bot = Bot(
            token=self._token, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self._bot = self.bot  # backwards compat i assume?
        self._dp = Dispatcher()

        try:
            bot_me = await self.bot.get_me()
            self.bot_username = typing.cast(str, bot_me.username)
            self.bot_id = bot_me.id
        except TelegramUnauthorizedError:
            logger.critical("Token expired, revoking...")
            await self._dp_revoke_token(False)
            return

        try:
            m = await self._client.send_message(self.bot_username, "/start hikka init")
        except (pyrogram.errors.InputUserDeactivated, ValueError) as e:
            logger.error("resetting inline bot token", exc_info=e)
            self._db.set("hikka.inline", "bot_token", None)
            self._token = None

            if not after_break:
                await self.register_manager(True)
                return

            self.init_complete = False
            return
        except pyrogram.errors.YouBlockedUser:
            await self._client.unblock_user(self.bot_username)
            try:
                m = await self._client.send_message(
                    self.bot_username, "/start hikka init"
                )
            except Exception:
                logger.critical("Can't unblock users bot", exc_info=True)
                return
        except Exception:
            self.init_complete = False
            logger.critical("Initialization of inline manager failed!", exc_info=True)
            return

        await m.delete()

        self._dp.inline_query.register(
            self._inline_handler,
            lambda _: True,
        )

        self._dp.callback_query.register(
            self._callback_query_handler,
            lambda _: True,
        )

        self._dp.chosen_inline_result.register(
            self._chosen_inline_handler,
            lambda _: True,
        )

        self._dp.message.register(
            self._message_handler,
            lambda *_: True,
        )

        old = self.bot.get_updates
        revoke = self._dp_revoke_token

        async def new(*args, **kwargs):
            nonlocal revoke, old
            try:
                return await old(*args, **kwargs)
            except TelegramConflictError:
                logger.error("received TelegramConflictError, revoking inline token")
                await revoke()
            except TelegramUnauthorizedError:
                logger.critical("Got Unauthorized")
                await self._stop()

        self.bot.get_updates = new

        self._task = asyncio.ensure_future(self._dp.start_polling(self.bot))
        self._cleaner_task = asyncio.ensure_future(self._cleaner())
        return

    async def _stop(self):
        """Stop the bot"""
        self._task.cancel()
        await self._dp.stop_polling()
        self._cleaner_task.cancel()

    async def _invoke_unit(self, unit_id: str, message: Message) -> Message:
        event = asyncio.Event()
        self._error_events[unit_id] = event

        q: "BotResults" = None  # type: ignore  # noqa: F821
        exception: Exception | None = None

        async def result_getter():
            nonlocal unit_id, q
            with contextlib.suppress(Exception):
                q = await self._client.get_inline_bot_results(
                    self.bot_username, unit_id
                )

        async def event_poller():
            nonlocal exception
            await asyncio.wait_for(event.wait(), timeout=10)
            if self._error_events.get(unit_id):
                exception = self._error_events[unit_id]

        result_getter_task = asyncio.ensure_future(result_getter())
        event_poller_task = asyncio.ensure_future(event_poller())

        _, pending = await asyncio.wait(
            [result_getter_task, event_poller_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        self._error_events.pop(unit_id, None)

        if exception:
            raise exception  # skipcq: PYL-E0702

        if len(q.results) <= 0:
            raise Exception("No query results")

        return await self._client.send_inline_bot_result(
            utils.get_chat_id(message),
            q.query_id,
            q.results[0].id,
            reply_to_message_id=message.reply_to_message_id,
        )

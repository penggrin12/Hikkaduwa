# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import contextlib
import copy
import functools
import logging
import time
import traceback
import typing

import pyrogram.errors
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from pyrogram.types import Message

from .. import main, utils
from ..types import HikkaReplyMarkup
from .types import InlineMessage, InlineUnit

logger = logging.getLogger(__name__)


class InlineList(InlineUnit):
    async def __call__(
        self,
        message: Message | int,
        strings: list[str],
        *,
        force_me: bool = False,
        always_allow: list[int] | None = None,
        manual_security: bool = False,
        disable_security: bool = False,
        ttl: int | bool = False,
        on_unload: typing.Callable[[], typing.Any] | None = None,
        silent: bool = False,
        custom_buttons: HikkaReplyMarkup | None = None,
    ) -> InlineMessage | typing.Literal[False]:
        """
        Send inline list to chat
        :param message: Where to send list. Can be either `Message` or `int`
        :param strings: List of strings, which should become inline list
        :param force_me: Either this list buttons must be pressed only by owner scope or no
        :param always_allow: Users, that are allowed to press buttons in addition to previous rules
        :param ttl: Time, when the list is going to be unloaded. Unload means, that the list
                    will become unusable. Pay attention, that ttl can't
                    be bigger, than default one (1 day) and must be either `int` or `False`
        :param on_unload: Callback, called when list is unloaded and/or closed. You can clean up trash
                          or perform another needed action
        :param manual_security: By default, Hikkaduwa will try to inherit inline buttons security from the caller (command)
                                If you want to avoid this, pass `manual_security=True`
        :param disable_security: By default, Hikkaduwa will try to inherit inline buttons security from the caller (command)
                                 If you want to disable all security checks on this list in particular, pass `disable_security=True`
        :param silent: Whether the list must be sent silently (w/o "Opening list..." message)
        :param custom_buttons: Custom buttons to add above native ones
        :return: If list is sent, returns :obj:`InlineMessage`, otherwise returns `False`
        """
        with contextlib.suppress(AttributeError):
            _hikka_client_id_logging_tag = copy.copy(self._manager._client.tg_id)  # noqa: F841

        custom_buttons = self._manager.utils._validate_markup(custom_buttons)

        if not isinstance(manual_security, bool):
            logger.error(
                "Invalid type for `manual_security`. Expected `bool`, got `%s`",
                type(manual_security),
            )
            return False

        if not isinstance(silent, bool):
            logger.error(
                "Invalid type for `silent`. Expected `bool`, got `%s`",
                type(silent),
            )
            return False

        if not isinstance(disable_security, bool):
            logger.error(
                "Invalid type for `disable_security`. Expected `bool`, got `%s`",
                type(disable_security),
            )
            return False

        if not isinstance(message, (Message, int)):
            logger.error(
                "Invalid type for `message`. Expected `Message` or `int`, got `%s`",
                type(message),
            )
            return False

        if not isinstance(force_me, bool):
            logger.error(
                "Invalid type for `force_me`. Expected `bool`, got `%s`",
                type(force_me),
            )
            return False

        if not isinstance(strings, list) or not strings:
            logger.error(
                (
                    "Invalid type for `strings`. Expected `list` with at least one"
                    " element, got `%s`"
                ),
                type(strings),
            )
            return False

        if len(strings) > 50:
            logger.error("Too much pages for `strings` (%s)", len(strings))
            return False

        if always_allow and not isinstance(always_allow, list):
            logger.error(
                "Invalid type for `always_allow`. Expected `list`, got `%s`",
                type(always_allow),
            )
            return False

        if not always_allow:
            always_allow = []

        if not isinstance(ttl, int) and ttl:
            logger.error(
                "Invalid type for `ttl`. Expected `int` or `False`, got `%s`",
                type(ttl),
            )
            return False

        unit_id = utils.rand(16)

        self._manager._units[unit_id] = {
            "type": "list",
            "caller": message,
            "chat": None,
            "message_id": None,
            "top_msg_id": (
                utils.get_topic(message) if isinstance(message, Message) else None
            ),
            "uid": unit_id,
            "current_index": 0,
            "strings": strings,
            "future": asyncio.Event(),
            **({"ttl": round(time.time()) + ttl} if ttl else {}),
            **({"force_me": force_me} if force_me else {}),
            **({"disable_security": disable_security} if disable_security else {}),
            **({"on_unload": on_unload} if callable(on_unload) else {}),
            **({"always_allow": always_allow} if always_allow else {}),
            **({"message": message} if isinstance(message, Message) else {}),
            **({"custom_buttons": custom_buttons} if custom_buttons else {}),
        }

        btn_call_data = utils.rand(10)

        self._manager._custom_map[btn_call_data] = {
            "handler": functools.partial(
                self._list_page,
                unit_id=unit_id,
            ),
            **(
                {"ttl": self._manager._units[unit_id]["ttl"]}
                if "ttl" in self._manager._units[unit_id]
                else {}
            ),
            **({"always_allow": always_allow} if always_allow else {}),
            **({"force_me": force_me} if force_me else {}),
            **({"disable_security": disable_security} if disable_security else {}),
            **({"message": message} if isinstance(message, Message) else {}),
        }

        if isinstance(message, Message) and not silent:
            try:
                status_message = await (
                    message.edit if message.outgoing else message.answer
                )(text="🌘" + self._manager.translator.getkey("inline.opening_list"))
            except Exception:
                status_message = None
        else:
            status_message = None

        async def answer(msg: str):
            nonlocal message
            if isinstance(message, Message):
                await (message.edit if message.outgoing else message.answer)(text=msg)
            else:
                await self._manager._client.send_message(message, msg)

        try:
            m = await self._manager._invoke_unit(unit_id, message)
        except pyrogram.errors.ChatSendInlineForbidden:
            await answer(self._manager.translator.getkey("inline.inline403"))
            del self._manager._units[unit_id]
            return False
        except Exception:
            logger.exception("Can't send list")

            del self._manager._units[unit_id]
            await answer(
                self._manager.translator.getkey("inline.invoke_failed_logs").format(
                    utils.escape_html(
                        "\n".join(traceback.format_exc().splitlines()[1:])
                    )
                )
                if self._manager._db.get(main.__name__, "inlinelogs", True)
                else self._manager.translator.getkey("inline.invoke_failed")
            )

            return False

        await self._manager._units[unit_id]["future"].wait()
        del self._manager._units[unit_id]["future"]

        self._manager._units[unit_id]["chat"] = utils.get_chat_id_keep_minus100(m)
        self._manager._units[unit_id]["message_id"] = m.id

        if isinstance(message, Message) and message.outgoing:
            if message.outgoing:
                await message.delete()
            elif status_message:
                await status_message.delete()

        return InlineMessage(
            self._manager, unit_id, self._manager._units[unit_id]["inline_message_id"]
        )

    async def _list_page(
        self, call: CallbackQuery, page: int | str, unit_id: str
    ) -> None:
        if page == "close":
            await self._manager.utils._delete_unit_message(call, unit_id=unit_id)
            return

        if isinstance(page, str):
            raise ValueError('`page` cannot be a string unless its "close"')

        if self._manager._units[unit_id]["current_index"] < 0 or page >= len(
            self._manager._units[unit_id]["strings"]
        ):
            await call.answer("Can't go to this page", show_alert=True)
            return

        self._manager._units[unit_id]["current_index"] = page

        try:
            await self._manager.bot.edit_message_text(
                inline_message_id=call.inline_message_id,
                text=self._manager.utils.sanitise_text(
                    self._manager._units[unit_id]["strings"][
                        self._units[unit_id]["current_index"]
                    ]
                ),
                reply_markup=self._list_markup(unit_id),
            )
            await call.answer()
        except TelegramRetryAfter as e:
            await call.answer(
                f"Got FloodWait. Wait for {e.retry_after} seconds",
                show_alert=True,
            )
        except Exception:
            logger.exception("Exception while trying to edit list")
            await call.answer("Error occurred", show_alert=True)
            return

    def _list_markup(self, unit_id: str) -> InlineKeyboardMarkup | None:
        """Generates aiogram markup for `list`"""
        callback = functools.partial(self._list_page, unit_id=unit_id)
        return self._manager.utils.generate_markup(
            self._manager._units[unit_id].get("custom_buttons", [])
            + self._manager.utils.build_pagination(
                callback=callback,
                total_pages=len(self._manager._units[unit_id]["strings"]),
                unit_id=unit_id,
            )
            + [[{"text": "🔻 Close", "callback": callback, "args": ("close",)}]],
        )

    async def _list_inline_handler(self, inline_query: InlineQuery):
        for unit in self._manager._units.copy().values():
            if (
                inline_query.from_user.id == self._manager._me
                and inline_query.query == unit["uid"]
                and unit["type"] == "list"
            ):
                try:
                    await inline_query.answer(
                        [
                            InlineQueryResultArticle(
                                id=utils.rand(20),
                                title="Hikkaduwa",
                                input_message_content=InputTextMessageContent(
                                    message_text=self._manager.utils.sanitise_text(
                                        unit["strings"][0]
                                    ),
                                    parse_mode="HTML",
                                    disable_web_page_preview=True,
                                ),
                                reply_markup=self._list_markup(inline_query.query),
                            )
                        ],
                        cache_time=60,
                    )
                except Exception as e:
                    if unit["uid"] in self._manager._error_events:
                        self._manager._error_events[unit["uid"]].event.set()
                        self._manager._error_events[unit["uid"]].exception = e

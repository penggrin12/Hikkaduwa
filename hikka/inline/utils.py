# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import base64
import contextlib
import functools
import io
import itertools
import logging
import os
import re
import struct
import typing
from copy import deepcopy
from urllib.parse import urlparse

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNotFound,
    TelegramRetryAfter,
)
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAnimation,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pyrogram.errors import RPCError
from pyrogram.utils import ZERO_CHANNEL_ID

from .. import utils
from .types import BytesIOInputFile, InlineUnit

if typing.TYPE_CHECKING:
    from aiogram.types import CallbackQuery

    from ..types import HikkaReplyMarkup, InlineCall

logger = logging.getLogger(__name__)


def _unpack_inline_message_id(inline_message_id: str) -> tuple[int, int, int]:
    """
    :returns: (dc_id, message_id, chat_id)
    """

    # len(buff):
    # supergroup = 24
    # group & dm = 20

    typing.cast(str, None)

    padded: str = inline_message_id + "=" * (-len(inline_message_id) % 4)
    buff: bytes = base64.urlsafe_b64decode(padded)

    if len(buff) == 20:
        return struct.unpack("<iii", buff[:12])
    elif len(buff) == 24:
        # noinspection SpellCheckingInspection
        dc_id, chat_id, message_id, access_hash = struct.unpack("<iqiq", buff)
        return dc_id, message_id, chat_id
    raise ValueError("Invalid inline message id")


class InlineUtils(InlineUnit):
    def _generate_markup(
        self,
        markup_obj: "HikkaReplyMarkup | str | None",
    ) -> InlineKeyboardMarkup | None:
        """Generate markup for form or list of `dict`s"""
        if not markup_obj:
            return None

        if isinstance(markup_obj, InlineKeyboardMarkup):
            return markup_obj

        kb = InlineKeyboardBuilder()

        map_ = (
            self._manager._units[markup_obj]["buttons"]
            if isinstance(markup_obj, str)
            else markup_obj
        )

        map_ = self._normalize_markup(map_)

        setup_callbacks = False

        for row in map_:
            for button in row:
                if not isinstance(button, dict):
                    logger.error(
                        "Button %s is not a `dict`, but `%s` in %s",
                        button,
                        type(button),
                        map_,
                    )
                    return None

                if "callback" not in button:
                    if button.get("action") == "close":
                        button["callback"] = self._close_unit_handler
                    elif button.get("action") == "unload":
                        button["callback"] = self._unload_unit_handler
                    elif button.get("action") == "answer":
                        if not button.get("message"):
                            logger.error(
                                "Button %s has no `message` to answer with", button
                            )
                            return None

                        button["callback"] = functools.partial(
                            self._answer_unit_handler,
                            show_alert=button.get("show_alert", False),
                            text=button["message"],
                        )

                if "callback" in button and "_callback_data" not in button:
                    button["_callback_data"] = utils.rand(30)
                    setup_callbacks = True

                if "input" in button and "_switch_query" not in button:
                    button["_switch_query"] = utils.rand(10)

        for row in map_:
            line = []
            for button in row:
                try:
                    if "url" in button:
                        if not utils.check_url(button["url"]):
                            logger.warning(
                                "Button have not been added to form, "
                                "because its url is invalid"
                            )
                            continue

                        line += [
                            InlineKeyboardButton(
                                text=button["text"],
                                url=button["url"],
                            )
                        ]
                    elif "callback" in button:
                        line += [
                            InlineKeyboardButton(
                                text=str(button["text"]),
                                callback_data=button["_callback_data"],
                            )
                        ]
                        if setup_callbacks:
                            self._manager._custom_map[button["_callback_data"]] = {
                                "handler": button["callback"],
                                **(
                                    {"always_allow": button["always_allow"]}
                                    if button.get("always_allow", False)
                                    else {}
                                ),
                                **(
                                    {"args": button["args"]}
                                    if button.get("args", False)
                                    else {}
                                ),
                                **(
                                    {"kwargs": button["kwargs"]}
                                    if button.get("kwargs", False)
                                    else {}
                                ),
                                **(
                                    {"force_me": True}
                                    if button.get("force_me", False)
                                    else {}
                                ),
                            }
                    elif "input" in button:
                        line += [
                            InlineKeyboardButton(
                                text=button["text"],
                                switch_inline_query_current_chat=button["_switch_query"]
                                + " ",
                            )
                        ]
                    elif "data" in button:
                        line += [
                            InlineKeyboardButton(
                                text=button["text"],
                                callback_data=button["data"],
                            )
                        ]
                    elif "switch_inline_query_current_chat" in button:
                        line += [
                            InlineKeyboardButton(
                                text=button["text"],
                                switch_inline_query_current_chat=button[
                                    "switch_inline_query_current_chat"
                                ],
                            )
                        ]
                    elif "switch_inline_query" in button:
                        line += [
                            InlineKeyboardButton(
                                text=button["text"],
                                switch_inline_query_current_chat=button[
                                    "switch_inline_query"
                                ],
                            )
                        ]
                    else:
                        logger.warning(
                            (
                                "Button have not been added to "
                                "form, because it is not structured "
                                "properly. %s"
                            ),
                            button,
                        )
                except KeyError:
                    logger.exception(
                        "Error while forming markup! Probably, you "
                        "passed wrong type combination for button. "
                        "Contact developer of module."
                    )
                    return None

            kb.row(*line)

        return kb.as_markup()

    generate_markup = _generate_markup

    async def _close_unit_handler(self, call: "InlineCall"):
        await call.delete()

    async def _unload_unit_handler(self, call: "InlineCall"):
        await call.unload()

    async def _answer_unit_handler(
        self, call: "InlineCall", text: str, show_alert: bool
    ):
        await call.answer(text, show_alert=show_alert)

    def _reverse_method_lookup(self, needle: typing.Callable, /) -> str | None:
        return next(
            (
                name
                for name, method in itertools.chain(
                    self._manager._allmodules.inline_handlers.items(),
                    self._manager._allmodules.callback_handlers.items(),
                )
                if method == needle
            ),
            None,
        )

    async def check_inline_security(
        self, *, func: typing.Callable | None = None, user: int
    ) -> bool:
        """Checks if user with id `user` is allowed to run function `func`"""
        return user == self._manager._client._tg_id

    def normalize_markup(
        self, reply_markup: "HikkaReplyMarkup"
    ) -> list[list[dict[str, typing.Any]]]:
        if isinstance(reply_markup, dict):
            return [[reply_markup]]

        if isinstance(reply_markup, list) and any(
            isinstance(i, dict) for i in reply_markup
        ):
            return [reply_markup]  # type: ignore

        return reply_markup  # type: ignore

    _normalize_markup = normalize_markup

    def sanitise_text(self, text: str) -> str:
        """
        Replaces all animated emojis in text with normal ones,
        bc aiogram doesn't support them

        :param text: text to sanitize
        :return: sanitized text
        """
        return re.sub(r"</?(?:emoji|blockquote).*?>", "", text)

    async def _edit_unit(
        self,
        text: str | None = None,
        reply_markup: "HikkaReplyMarkup | None" = None,
        *,
        photo: str | None = None,
        file: str | None = None,
        video: str | None = None,
        audio: dict | str | None = None,
        gif: str | None = None,
        mime_type: str | None = None,
        force_me: bool | None = None,
        disable_security: bool | None = None,
        always_allow: list[int] | None = None,
        disable_web_page_preview: bool = True,
        query: "CallbackQuery | None" = None,
        unit_id: str | None = None,
        inline_message_id: str | None = None,
        chat_id: int | None = None,
        message_id: int | None = None,
    ) -> bool:
        """
        Edits unit message
        :param text: Text of message
        :param reply_markup: Inline keyboard
        :param photo: Url to a valid photo to attach to message
        :param file: Url to a valid file to attach to message
        :param video: Url to a valid video to attach to message
        :param audio: Url to a valid audio to attach to message
        :param gif: Url to a valid GIF to attach to message
        :param mime_type: Mime type of file
        :param force_me: Allow only userbot owner to interact with buttons
        :param disable_security: Disable security check for buttons
        :param always_allow: List of user ids, which will always be allowed
        :param disable_web_page_preview: Disable web page preview
        :param query: Callback query
        :return: Status of edit
        """
        reply_markup = self._validate_markup(reply_markup) or []

        if text is not None and not isinstance(text, str):
            logger.error(
                "Invalid type for `text`. Expected `str`, got `%s`", type(text)
            )
            return False

        if file and not mime_type:
            logger.error(
                "You must pass `mime_type` along with `file` field\n"
                "It may be either 'application/zip' or 'application/pdf'"
            )
            return False

        if isinstance(audio, str):
            audio = {"url": audio}

        if isinstance(text, str):
            text = self.sanitise_text(text)

        media_params = [
            photo is None,
            gif is None,
            file is None,
            video is None,
            audio is None,
        ]

        if media_params.count(False) > 1:
            logger.error("You passed two or more exclusive parameters simultaneously")
            return False

        if unit_id is not None and unit_id in self._manager._units:
            unit = self._manager._units[unit_id]

            unit["buttons"] = reply_markup

            if isinstance(force_me, bool):
                unit["force_me"] = force_me

            if isinstance(disable_security, bool):
                unit["disable_security"] = disable_security

            if isinstance(always_allow, list):
                unit["always_allow"] = always_allow
        else:
            unit = {}

        if not chat_id or not message_id:
            inline_message_id = (
                inline_message_id
                or unit.get("inline_message_id", False)
                or getattr(query, "inline_message_id", None)
            )

        if not chat_id and not message_id and not inline_message_id:
            logger.warning(
                "Attempted to edit message with no `inline_message_id`. "
                "Possible reasons:\n"
                "- Form was sent without buttons and due to "
                "the limits of Telegram API can't be edited\n"
                "- There is an in-userbot error, which you should report"
            )
            return False

        try:
            path = urlparse(photo).path
            ext = os.path.splitext(path)[1]
        except Exception:
            ext = None

        if photo is not None and ext in {".gif", ".mp4"}:
            gif = deepcopy(photo)
            photo = None

        media = next(
            (media for media in [photo, file, video, audio, gif] if media), None
        )

        if isinstance(media, bytes):
            media = io.BytesIO(media)
            media.name = "upload.mp4"

        if isinstance(media, io.BytesIO):
            media = BytesIOInputFile(media)

        if file:
            media = InputMediaDocument(media=media, caption=text, parse_mode="HTML")
        elif photo:
            media = InputMediaPhoto(media=media, caption=text, parse_mode="HTML")
        elif audio:
            if isinstance(audio, dict):
                media = InputMediaAudio(
                    media=audio["url"],
                    title=audio.get("title"),
                    performer=audio.get("performer"),
                    duration=audio.get("duration"),
                    caption=text,
                    parse_mode="HTML",
                )
            else:
                media = InputMediaAudio(
                    media=audio,
                    caption=text,
                    parse_mode="HTML",
                )
        elif video:
            media = InputMediaVideo(media=media, caption=text, parse_mode="HTML")
        elif gif:
            media = InputMediaAnimation(media=media, caption=text, parse_mode="HTML")

        if media is None and text is None and reply_markup:
            try:
                await self._manager.bot.edit_message_reply_markup(
                    **(
                        {"inline_message_id": inline_message_id}
                        if inline_message_id
                        else {"chat_id": chat_id, "message_id": message_id}
                    ),
                    reply_markup=self.generate_markup(reply_markup),
                )
            except Exception:
                return False

            return True

        if media is None and text is None:
            logger.error("You must pass either `text` or `media` or `reply_markup`")
            return False

        if media is None:
            try:
                await self._manager.bot.edit_message_text(
                    text,
                    **(
                        {"inline_message_id": inline_message_id}
                        if inline_message_id
                        else {"chat_id": chat_id, "message_id": message_id}
                    ),
                    disable_web_page_preview=disable_web_page_preview,
                    reply_markup=self.generate_markup(
                        reply_markup
                        if isinstance(reply_markup, list)
                        else unit.get("buttons", [])
                    ),
                )
            except TelegramRetryAfter as e:
                logger.info("Sleeping %ss on aiogram FloodWait...", e.retry_after)
                await asyncio.sleep(e.retry_after)
                return await self._edit_unit(**utils.get_kwargs())
            except TelegramNotFound:
                if query:
                    with contextlib.suppress(Exception):
                        await query.answer(
                            "I should have edited some message, but it is deleted :("
                        )

                return False
            except TelegramBadRequest as e:
                if "messagenotmodified" in e.message.casefold():
                    if query:
                        with contextlib.suppress(Exception):
                            await query.answer()

                    return False

                if "There is no text in the message to edit" not in str(e):
                    raise

                try:
                    await self._manager.bot.edit_message_caption(
                        caption=text,
                        **(
                            {"inline_message_id": inline_message_id}
                            if inline_message_id
                            else {"chat_id": chat_id, "message_id": message_id}
                        ),
                        reply_markup=self.generate_markup(
                            reply_markup
                            if isinstance(reply_markup, list)
                            else unit.get("buttons", [])
                        ),
                    )
                except Exception:
                    return False
                else:
                    return True
            else:
                return True

        try:
            await self._manager.bot.edit_message_media(
                **(
                    {"inline_message_id": inline_message_id}
                    if inline_message_id
                    else {"chat_id": chat_id, "message_id": message_id}
                ),
                media=media,
                reply_markup=self.generate_markup(
                    reply_markup
                    if isinstance(reply_markup, list)
                    else unit.get("buttons", [])
                ),
            )
        except TelegramRetryAfter as e:
            logger.info("Sleeping %ss on aiogram FloodWait...", e.retry_after)
            await asyncio.sleep(e.retry_after)
            return await self._edit_unit(**utils.get_kwargs())
        except TelegramNotFound:
            with contextlib.suppress(Exception):
                await query.answer(
                    "I should have edited some message, but it is deleted :("
                )
            return False
        else:
            return True

    async def _delete_unit_message(
        self,
        call: "CallbackQuery | None" = None,
        unit_id: str | None = None,
        chat_id: int | None = None,
        message_id: int | None = None,
    ) -> bool:
        """Params `self`, `unit_id` are for internal use only, do not try to pass them"""
        if getattr(getattr(call, "message", None), "chat", None):
            try:
                await self._manager.bot.delete_message(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                )
            except TelegramAPIError as e:
                logging.error("Failed to delete an inline message", exc_info=e)
                return False

            return True

        if chat_id and message_id:
            try:
                await self._manager.bot.delete_message(
                    chat_id=chat_id, message_id=message_id
                )
            except TelegramAPIError as e:
                logging.error("Failed to delete an inline message", exc_info=e)
                return False

            return True

        if not unit_id and hasattr(call, "unit_id") and call.unit_id:
            unit_id = call.unit_id

        try:
            _, message_id, chat_id = _unpack_inline_message_id(
                self._manager._units[unit_id]["inline_message_id"]
            )
            # it seems to always need a -100 prefix if its negative
            # should it be in the helper function?
            if chat_id < 0:
                chat_id = ZERO_CHANNEL_ID + chat_id

            await self._manager._client.delete_messages(chat_id, [message_id])
            await self._unload_unit(unit_id)
        except RPCError as e:
            logging.error("Failed to delete an inline message", exc_info=e)
            return False

        return True

    async def _unload_unit(self, unit_id: str) -> bool:
        """Params `self`, `unit_id` are for internal use only, do not try to pass them"""
        try:
            if "on_unload" in self._manager._units[unit_id] and callable(
                self._manager._units[unit_id]["on_unload"]
            ):
                self._manager._units[unit_id]["on_unload"]()

            if unit_id in self._manager._units:
                del self._manager._units[unit_id]
            else:
                return False
        except Exception:
            return False

        return True

    def build_pagination(
        self,
        callback: typing.Callable[[int], typing.Awaitable[typing.Any]],
        total_pages: int,
        unit_id: str | None = None,
        current_page: int | None = None,
    ) -> list[list[dict[str, typing.Any]]]:
        # Based on https://github.com/pystorage/pykeyboard/blob/master/pykeyboard/inline_pagination_keyboard.py#L4
        if current_page is None:
            if unit_id is None:
                raise ValueError("unit_id cannot be None if current_page is None")
            current_page = self._manager._units[unit_id]["current_index"] + 1

        if total_pages <= 5:
            return [
                [
                    (
                        {"text": number, "args": (number - 1,), "callback": callback}
                        if number != current_page
                        else {
                            "text": f"· {number} ·",
                            "args": (number - 1,),
                            "callback": callback,
                        }
                    )
                    for number in range(1, total_pages + 1)
                ]
            ]

        if current_page <= 3:
            return [
                [
                    (
                        {
                            "text": f"· {number} ·",
                            "args": (number - 1,),
                            "callback": callback,
                        }
                        if number == current_page
                        else (
                            {
                                "text": f"{number} ›",
                                "args": (number - 1,),
                                "callback": callback,
                            }
                            if number == 4
                            else (
                                {
                                    "text": f"{total_pages} »",
                                    "args": (total_pages - 1,),
                                    "callback": callback,
                                }
                                if number == 5
                                else {
                                    "text": number,
                                    "args": (number - 1,),
                                    "callback": callback,
                                }
                            )
                        )
                    )
                    for number in range(1, 6)
                ]
            ]

        if current_page > total_pages - 3:
            return [
                [
                    {"text": "« 1", "args": (0,), "callback": callback},
                    {
                        "text": f"‹ {total_pages - 3}",
                        "args": (total_pages - 4,),
                        "callback": callback,
                    },
                ]
                + [
                    (
                        {
                            "text": f"· {number} ·",
                            "args": (number - 1,),
                            "callback": callback,
                        }
                        if number == current_page
                        else {
                            "text": number,
                            "args": (number - 1,),
                            "callback": callback,
                        }
                    )
                    for number in range(total_pages - 2, total_pages + 1)
                ]
            ]

        return [
            [
                {"text": "« 1", "args": (0,), "callback": callback},
                {
                    "text": f"‹ {current_page - 1}",
                    "args": (current_page - 2,),
                    "callback": callback,
                },
                {
                    "text": f"· {current_page} ·",
                    "args": (current_page - 1,),
                    "callback": callback,
                },
                {
                    "text": f"{current_page + 1} ›",
                    "args": (current_page,),
                    "callback": callback,
                },
                {
                    "text": f"{total_pages} »",
                    "args": (total_pages - 1,),
                    "callback": callback,
                },
            ]
        ]

    def _validate_markup(
        self, buttons: "HikkaReplyMarkup | None" = None
    ) -> list[list[dict[str, typing.Any]]] | None:
        if buttons is None:
            buttons = []

        if not isinstance(buttons, (list, dict)):
            logger.error(
                "Reply markup ommited because passed type is not valid (%s)",
                type(buttons),
            )
            return None

        buttons = self._normalize_markup(buttons)

        if not all(all(isinstance(button, dict) for button in row) for row in buttons):
            logger.error(
                "Reply markup ommited because passed invalid type for one of the"
                " buttons"
            )
            return None

        if not all(
            all(
                "url" in button
                or "callback" in button
                or "input" in button
                or "data" in button
                or "action" in button
                for button in row
            )
            for row in buttons
        ):
            logger.error(
                "Invalid button specified. "
                "Button must contain one of the following fields:\n"
                "  - `url`\n"
                "  - `callback`\n"
                "  - `input`\n"
                "  - `data`\n"
                "  - `action`"
            )
            return None

        return buttons

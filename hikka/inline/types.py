# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html
import io
import logging
import typing

from aiogram import Bot
from aiogram.types import (
    CallbackQuery,
    InlineQueryResultArticle,
    InputFile,
    InputTextMessageContent,
)
from aiogram.types import InlineQuery as AiogramInlineQuery
from aiogram.types import Message as AiogramMessage
from aiogram.types.input_file import DEFAULT_CHUNK_SIZE

from .. import utils

if typing.TYPE_CHECKING:
    from hikka.inline.core import InlineManager

logger = logging.getLogger(__name__)


class InlineMessage:
    """Aiogram message, sent via inline bot"""

    if typing.TYPE_CHECKING:
        inline_message_id: str
        unit_id: str
        inline_manager: "InlineManager"
        _units: dict[str, dict]
        form: dict[str, typing.Any]

    def __init__(
        self,
        inline_manager: "InlineManager",  # type: ignore  # noqa: F821
        unit_id: str,
        inline_message_id: str,
    ):
        # bypass frozen pydantic fields
        self.__dict__.update(
            {
                "inline_message_id": inline_message_id,
                "unit_id": unit_id,
                "inline_manager": inline_manager,
                "_units": inline_manager._units,
                "form": {"id": unit_id, **inline_manager._units[unit_id]}
                if unit_id in inline_manager._units
                else {},
            }
        )

    async def edit(self, *args, **kwargs) -> "InlineMessage":
        if "unit_id" in kwargs:
            kwargs.pop("unit_id")

        if "inline_message_id" in kwargs:
            kwargs.pop("inline_message_id")

        await self.inline_manager.utils._edit_unit(
            *args,
            unit_id=self.unit_id,
            inline_message_id=self.inline_message_id,
            **kwargs,
        )

        return self

    async def delete(self) -> bool:
        return await self.inline_manager.utils._delete_unit_message(
            self,
            unit_id=self.unit_id,
        )

    async def unload(self) -> bool:
        return await self.inline_manager.utils._unload_unit(unit_id=self.unit_id)


class BotInlineMessage:
    """Aiogram message, sent through inline bot itself"""

    if typing.TYPE_CHECKING:
        chat_id: int
        unit_id: str
        inline_manager: "InlineManager"
        message_id: int
        _units: dict[str, dict]
        form: dict[str, typing.Any]

    def __init__(
        self,
        inline_manager: "InlineManager",  # type: ignore  # noqa: F821
        unit_id: str,
        chat_id: int,
        message_id: int,
    ):
        # bypass frozen pydantic fields
        self.__dict__.update(
            {
                "chat_id": chat_id,
                "unit_id": unit_id,
                "inline_manager": inline_manager,
                "message_id": message_id,
                "_units": inline_manager._units,
                "form": (
                    {"id": unit_id, **inline_manager._units[unit_id]}
                    if unit_id in inline_manager._units
                    else {}
                ),
            }
        )

    async def edit(self, *args, **kwargs) -> "BotMessage":
        if "unit_id" in kwargs:
            kwargs.pop("unit_id")

        if "message_id" in kwargs:
            kwargs.pop("message_id")

        if "chat_id" in kwargs:
            kwargs.pop("chat_id")

        await self.inline_manager.utils._edit_unit(
            *args,
            unit_id=self.unit_id,
            chat_id=self.chat_id,
            message_id=self.message_id,
            **kwargs,
        )

        return self

    async def delete(self) -> bool:
        return await self.inline_manager.utils._delete_unit_message(
            self,
            unit_id=self.unit_id,
            chat_id=self.chat_id,
            message_id=self.message_id,
        )

    async def unload(self, *args, **kwargs) -> bool:
        if "unit_id" in kwargs:
            kwargs.pop("unit_id")

        return await self.inline_manager.utils._unload_unit(
            *args,
            unit_id=self.unit_id,
            **kwargs,
        )


class InlineCall(CallbackQuery, InlineMessage):
    """Modified version of classic aiogram `CallbackQuery`"""

    if typing.TYPE_CHECKING:
        original_call: CallbackQuery

    def __init__(
        self,
        call: CallbackQuery,
        inline_manager: "InlineManager",  # type: ignore  # noqa: F821
        unit_id: str,
    ):
        # bypass frozen pydantic fields
        self.__dict__["original_call"] = call
        CallbackQuery.__init__(self, **call.model_dump())

        InlineMessage.__init__(
            self,
            inline_manager,
            unit_id,
            call.inline_message_id,
        )


class BotInlineCall(CallbackQuery, BotInlineMessage):
    """Modified version of classic aiogram `CallbackQuery`"""

    if typing.TYPE_CHECKING:
        original_call: CallbackQuery

    def __init__(
        self,
        call: CallbackQuery,
        inline_manager: "InlineManager",  # type: ignore  # noqa: F821
        unit_id: str,
    ):
        # bypass frozen pydantic fields
        self.__dict__["original_call"] = call
        CallbackQuery.__init__(self, **call.model_dump())

        BotInlineMessage.__init__(
            self,
            inline_manager,
            unit_id,
            call.message.chat.id,
            call.message.message_id,
        )


class InlineUnit:
    """InlineManager extension type. For internal use only"""

    def __init__(self, manager: "InlineManager") -> None:
        self._manager: "InlineManager" = manager


class BotMessage(AiogramMessage):
    """Modified version of original Aiogram Message"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)


class InlineQuery(AiogramInlineQuery):
    """Modified version of original Aiogram InlineQuery"""

    if typing.TYPE_CHECKING:
        inline_query: "InlineQuery"
        args: str

    def __init__(self, inline_query: AiogramInlineQuery):
        AiogramInlineQuery.__init__(self, **inline_query.model_dump())

        self.__dict__.update(
            {
                "inline_query": inline_query,
                "args": (
                    inline_query.query.split(maxsplit=1)[1]
                    if len(inline_query.query.split()) > 1
                    else ""
                ),
            }
        )

    @staticmethod
    def _get_res(title: str, description: str, thumb_url: str) -> list:
        return [
            InlineQueryResultArticle(
                id=utils.rand(20),
                title=title,
                description=description,
                input_message_content=InputTextMessageContent(
                    "😶‍🌫️ <i>There is nothing here...</i>",
                    parse_mode="HTML",
                ),
                thumbnail_url=thumb_url,
                thumbnail_width=128,
                thumbnail_height=128,
            )
        ]

    async def e400(self):
        await self.answer(
            self._get_res(
                "🚫 400",
                "Bad request. You need to pass right arguments, follow module's documentation",
                "https://img.icons8.com/color/344/swearing-male--v1.png",
            ),
            cache_time=0,
        )

    async def e403(self):
        await self.answer(
            self._get_res(
                "🚫 403",
                "You have no permissions to access this result",
                "https://img.icons8.com/external-wanicon-flat-wanicon/344/external-forbidden-new-normal-wanicon-flat-wanicon.png",
            ),
            cache_time=0,
        )

    async def e404(self):
        await self.answer(
            self._get_res(
                "🚫 404",
                "No results found",
                "https://img.icons8.com/external-justicon-flat-justicon/344/external-404-error-responsive-web-design-justicon-flat-justicon.png",
            ),
            cache_time=0,
        )

    async def e426(self):
        await self.answer(
            self._get_res(
                "🚫 426",
                "You need to update Hikkaduwa before sending this request",
                "https://img.icons8.com/fluency/344/approve-and-update.png",
            ),
            cache_time=0,
        )

    async def e500(self):
        await self.answer(
            self._get_res(
                "🚫 500",
                "Internal userbot error while processing request. More info in logs",
                "https://img.icons8.com/external-vitaliy-gorbachev-flat-vitaly-gorbachev/344/external-error-internet-security-vitaliy-gorbachev-flat-vitaly-gorbachev.png",
            ),
            cache_time=0,
        )


class BytesIOInputFile(InputFile):
    def __init__(self, file: io.BytesIO, chunk_size: int = DEFAULT_CHUNK_SIZE):
        """
        :param chunk_size: Uploading chunk size
        """
        name: typing.Any | None = getattr(file, "name", None)
        super().__init__(filename=str(name) if name else None, chunk_size=chunk_size)

        self.file: io.BytesIO = file

    async def read(self, bot: Bot) -> typing.AsyncGenerator[bytes, None]:
        while chunk := self.file.read(self.chunk_size):
            yield chunk

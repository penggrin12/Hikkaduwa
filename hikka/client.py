import typing

from pyrogram import Client as BaseClient
from pyrogram import types

if typing.TYPE_CHECKING:
    from hikka.database import Database
    from hikka.dispatcher import CommandDispatcher
    from hikka.inline.core import InlineManager
    from hikka.loader import Modules
    from hikka.translations import BaseTranslator

    class ChannelCache(typing.TypedDict):
        peer: types.Chat
        exp: int


class HikkaClient(BaseClient):
    def __init__(self, /, **kwargs) -> None:
        self.hikka_inline: "InlineManager" = None  # type: ignore
        self.hikka_db: "Database" = None  # type: ignore
        # just `dispatcher` collides with base
        self.hikka_dispatcher: "CommandDispatcher"  # type: ignore
        self._loader: "Modules" = None  # type: ignore
        self.translator: "BaseTranslator" = None  # type: ignore

        self.tg_id: int = 0

        self.use_qr: bool = False

        self._channels_cache: dict[str, "ChannelCache"] = {}

        super().__init__(**kwargs)

    @property
    def channels_cache(self) -> dict[str, "ChannelCache"]:
        return self._channels_cache

    @property
    def loader(self) -> "Modules":
        return self._loader

    @property
    def _tg_id(self) -> int:
        return self.tg_id

    @property
    def hikka_me(self) -> types.User:
        return typing.cast(types.User, self.me)

    async def __aenter__(self) -> "HikkaClient":
        return await self.start(use_qr=self.use_qr)

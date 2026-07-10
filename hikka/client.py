import typing

import pyrogram

if typing.TYPE_CHECKING:
    from hikka.database import Database
    from hikka.dispatcher import CommandDispatcher
    from hikka.inline.core import InlineManager
    from hikka.loader import Modules

    class ChannelCache(typing.TypedDict):
        peer: pyrogram.types.Chat
        exp: int


class HikkaClient(pyrogram.Client):
    def __init__(self, /, **kwargs):
        self.hikka_inline: "InlineManager"
        self.hikka_db: "Database"
        # just `dispatcher` collides with base
        self.hikka_dispatcher: "CommandDispatcher"
        self._loader: "Modules | None" = None

        self.tg_id: int

        self.use_qr: bool = False

        self._channels_cache: dict[str, ChannelCache] = {}

        super().__init__(**kwargs)

    @property
    def channels_cache(self):
        return self._channels_cache

    @property
    def loader(self) -> "Modules":
        return typing.cast("Modules", self._loader)

    @property
    def _tg_id(self) -> int:
        return self.tg_id  # type: ignore

    @property
    def hikka_me(self) -> pyrogram.types.User:
        return typing.cast(pyrogram.types.User, self.me)

    async def __aenter__(self):
        return await self.start(use_qr=self.use_qr)

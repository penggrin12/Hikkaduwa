# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import collections
import logging
import time
import typing

import orjson
import pyrogram
from pyrogram.errors import ChannelsTooMuch
from pyrogram.types import Message

from . import main, utils
from .pointers import (
    BaseSerializingMiddlewareDict,
    BaseSerializingMiddlewareList,
    NamedTupleMiddlewareDict,
    NamedTupleMiddlewareList,
    PointerDict,
    PointerList,
)

if typing.TYPE_CHECKING:
    from .client import HikkaClient
    from .types import JSONSerializable

__all__ = [
    "Database",
    "PointerList",
    "PointerDict",
    "NamedTupleMiddlewareDict",
    "NamedTupleMiddlewareList",
    "BaseSerializingMiddlewareDict",
    "BaseSerializingMiddlewareList",
]

logger = logging.getLogger(__name__)


class NoAssetsChannel(Exception):
    """Raised when trying to read/store asset with no asset channel present"""


class Database(dict):
    def __init__(self, /, client: "HikkaClient"):
        super().__init__()
        self._client: "HikkaClient" = client
        self._next_revision_call: int = 0
        self._revisions: list[dict] = []
        self._assets: int | None = None
        self._me: pyrogram.types.User = client.hikka_me
        self._redis: None = None
        self._saving_task: asyncio.Future | None = None

    def __repr__(self) -> str:
        return object.__repr__(self)

    def _redis_save_sync(self) -> None:
        return

    async def remote_force_save(self) -> bool:
        return False

    async def _redis_save(self) -> bool:
        return False

    async def redis_init(self) -> bool:
        return False

    async def init(self) -> None:
        """Asynchronous initialization unit"""
        self._db_file = main.BASE_PATH / f"config-{self._client.tg_id}.json"
        self.read()

        try:
            self._assets, _ = await utils.asset_channel(
                self._client,
                "hikka-assets",
                "🌆 Your Hikkaduwa assets will be stored here",
                archive=True,
                avatar="https://raw.githubusercontent.com/hikariatama/assets/master/hikka-assets.png",
            )
        except ChannelsTooMuch:
            self._assets = None
            logger.error(
                "Can't find and/or create assets folder\n"
                "This may cause several consequences, such as:\n"
                "- Non working assets feature (e.g. notes)\n"
                "- This error will occur every restart\n\n"
                "You can solve this by leaving some channels/groups"
            )

    def read(self) -> None:
        """Read database and stores it in self"""
        try:
            self.update(**orjson.loads(self._db_file.read_text(encoding="utf-8")))
        except orjson.JSONDecodeError:
            logger.warning("Database read failed! Creating new one...")
        except FileNotFoundError:
            logger.debug("Database file not found, creating new one...")

    def process_db_autofix(self, db: dict) -> bool:
        if not utils.is_serializable(db):
            return False

        for key, value in db.copy().items():
            if not isinstance(key, (str, int)):
                logger.warning(
                    "DbAutoFix: Dropped key %s, because it is not string or int",
                    key,
                )
                continue

            if not isinstance(value, dict):
                # If value is not a dict (module values), drop it,
                # otherwise it may cause problems
                del db[key]
                logger.warning(
                    "DbAutoFix: Dropped key %s, because it is non-dict, but %s",
                    key,
                    type(value),
                )
                continue

            for subkey in value:
                if not isinstance(subkey, (str, int)):
                    del db[key][subkey]
                    logger.warning(
                        (
                            "DbAutoFix: Dropped subkey %s of db key %s, because it is"
                            " not string or int"
                        ),
                        subkey,
                        key,
                    )
                    continue

        return True

    def save(self) -> bool:
        """Save database"""
        if not self.process_db_autofix(self):
            try:
                rev = self._revisions.pop()
                while not self.process_db_autofix(rev):
                    rev = self._revisions.pop()
            except IndexError:
                raise RuntimeError(
                    "Can't find revision to restore broken database from "
                    "database is most likely broken and will lead to problems, "
                    "so its save is forbidden."
                )

            self.clear()
            self.update(**rev)

            raise RuntimeError(
                "Rewriting database to the last revision because new one destructed it"
            )

        curr_time = int(time.time())
        if self._next_revision_call < curr_time:
            self._revisions += [dict(self)]
            self._next_revision_call = curr_time + 3

        while len(self._revisions) > 15:
            self._revisions.pop()

        try:
            self._db_file.write_bytes(orjson.dumps(self))
        except OSError as e:
            logger.error("Database save failed!", exc_info=e)
            return False

        return True

    async def store_asset(self, message: Message | str | typing.BinaryIO) -> int:
        """
        Save assets
        returns asset_id as integer
        """
        if not self._assets:
            raise NoAssetsChannel("Tried to save asset to non-existing asset channel")

        if isinstance(message, Message) and (not message.document):
            raise Exception("Can't save asset with no document")

        # noinspection PyUnresolvedReferences
        if not (
            msg := await self._client.send_document(
                chat_id=self._assets,
                document=(
                    message.document.file_id
                    if isinstance(message, Message)
                    else message
                ),
                force_document=True,
            )
        ):
            raise Exception("Asset couldn't be saved")

        return msg.id

    async def fetch_asset(self, asset_id: int) -> Message | None:
        """Fetch previously saved asset by its asset_id"""
        if not self._assets:
            raise NoAssetsChannel(
                "Tried to fetch asset from non-existing asset channel"
            )

        assets = await self._client.get_messages(
            chat_id=self._assets, message_ids=[asset_id]
        )

        return assets[0] if assets else None

    # noinspection PyMethodOverriding
    def get(
        self, owner: str, key: str, default: typing.Any | None = None
    ) -> "JSONSerializable":
        """Get database key"""
        try:
            value = self[owner][key]
            return value
        except KeyError:
            return default

    def set(self, owner: str, key: str, value: "JSONSerializable") -> bool:
        """Set database key"""
        if not utils.is_serializable(owner):
            raise RuntimeError(
                "Attempted to write object to "
                f"{owner=} ({type(owner)=}) of database. It is not "
                "JSON-serializable key which will cause errors"
            )

        if not utils.is_serializable(key):
            raise RuntimeError(
                "Attempted to write object to "
                f"{key=} ({type(key)=}) of database. It is not "
                "JSON-serializable key which will cause errors"
            )

        if not utils.is_serializable(value):
            raise RuntimeError(
                "Attempted to write object of "
                f"{key=} ({type(value)=}) to database. It is not "
                "JSON-serializable value which will cause errors"
            )

        super().setdefault(owner, {})[key] = value
        return self.save()

    def pointer(
        self,
        owner: str,
        key: str,
        default: "JSONSerializable | None" = None,
        item_type: typing.Any | None = None,
    ) -> "JSONSerializable | PointerList | PointerDict":
        """Get a pointer to database key"""
        value = self.get(owner, key, default)
        mapping = {
            list: PointerList,
            dict: PointerDict,
            collections.abc.Hashable: lambda v: v,
        }

        pointer_constructor = next(
            (pointer for type_, pointer in mapping.items() if isinstance(value, type_)),
            None,
        )

        if pointer_constructor is None:
            raise ValueError(
                f"Pointer for type {type(value).__name__} is not implemented"
            )

        if item_type is not None:
            if isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        raise ValueError(
                            "Item type can only be specified for dedicated keys and"
                            " can't be mixed with other ones"
                        )

                return NamedTupleMiddlewareList(
                    pointer_constructor(self, owner, key, default),
                    item_type,
                )
            if isinstance(value, dict):
                for item in self.get(owner, key, default).values():
                    if not isinstance(item, dict):
                        raise ValueError(
                            "Item type can only be specified for dedicated keys and"
                            " can't be mixed with other ones"
                        )

                return NamedTupleMiddlewareDict(
                    pointer_constructor(self, owner, key, default),
                    item_type,
                )

        return pointer_constructor(self, owner, key, default)

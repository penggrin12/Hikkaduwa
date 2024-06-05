# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import contextlib
import itertools
import os
import sys
import typing
from types import ModuleType

import hikkatl
from hikkatl.errors.rpcerrorlist import MessageIdInvalidError
from hikkatl.sessions import StringSession
from hikkatl.tl.types import Message
from meval import meval

from .. import loader, main, utils
from ..log import HikkaException


@loader.tds
class Evaluator(loader.Module):
    """Evaluates code in various languages"""

    strings = {"name": "Evaluator"}

    @loader.command(alias="eval")
    async def e(self, message: Message):
        try:
            result = await meval(
                utils.get_args_raw(message),
                globals(),
                **await self.getattrs(message),
            )
        except Exception:
            item = HikkaException.from_exc_info(*sys.exc_info())

            await utils.answer(
                message,
                self.strings("err").format(
                    "4985626654563894116",
                    utils.escape_html(utils.get_args_raw(message)),
                    self.censor(
                        (
                            "\n".join(item.full_stack.splitlines()[:-1])
                            + "\n\n"
                            + "🚫 "
                            + item.full_stack.splitlines()[-1]
                        )
                    ),
                ),
            )

            return

        if callable(getattr(result, "stringify", None)):
            with contextlib.suppress(Exception):
                result = str(result.stringify())

        with contextlib.suppress(MessageIdInvalidError):
            await utils.answer(
                message,
                self.strings("eval").format(
                    "4985626654563894116",
                    utils.escape_html(utils.get_args_raw(message)),
                    utils.escape_html(self.censor(str(result))),
                ),
            )

    def censor(self, ret: str) -> str:
        ret = ret.replace(str(self._client.hikka_me.phone), "&lt;phone&gt;")

        if redis := os.environ.get("REDIS_URL") or main.get_config_key("redis_uri"):
            ret = ret.replace(redis, f'redis://{"*" * 26}')

        if db := os.environ.get("DATABASE_URL") or main.get_config_key("db_uri"):
            ret = ret.replace(db, f'postgresql://{"*" * 26}')

        if btoken := self._db.get("hikka.inline", "bot_token", False):
            ret = ret.replace(
                btoken,
                f'{btoken.split(":")[0]}:{"*" * 26}',
            )

        if htoken := self.lookup("loader").get("token", False):
            ret = ret.replace(htoken, f'eugeo_{"*" * 26}')

        ret = ret.replace(
            StringSession.save(self._client.session),
            "StringSession(**************************)",
        )

        return ret

    async def getattrs(self, message: Message) -> dict:
        reply = await message.get_reply_message()
        return {
            "message": message,
            "client": self._client,
            "reply": reply,
            "r": reply,
            **self.get_sub(hikkatl.tl.types),
            **self.get_sub(hikkatl.tl.functions),
            "event": message,
            "chat": message.to_id,
            "hikkatl": hikkatl,
            "telethon": hikkatl,
            "utils": utils,
            "main": main,
            "loader": loader,
            "f": hikkatl.tl.functions,
            "c": self._client,
            "m": message,
            "lookup": self.lookup,
            "self": self,
            "db": self.db,
        }

    def get_sub(self, obj: typing.Any, _depth: int = 1) -> dict:
        """Get all callable capitalised objects in an object recursively, ignoring _*"""
        return {
            **dict(
                filter(
                    lambda x: x[0][0] != "_"
                    and x[0][0].upper() == x[0][0]
                    and callable(x[1]),
                    obj.__dict__.items(),
                )
            ),
            **dict(
                itertools.chain.from_iterable(
                    [
                        self.get_sub(y[1], _depth + 1).items()
                        for y in filter(
                            lambda x: x[0][0] != "_"
                            and isinstance(x[1], ModuleType)
                            and x[1] != obj
                            and x[1].__package__.rsplit(".", _depth)[0] == "hikkatl.tl",
                            obj.__dict__.items(),
                        )
                    ]
                )
            ),
        }

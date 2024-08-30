# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import re
from typing import Callable, Optional

from telethon.errors.rpcerrorlist import YouBlockedUserError  # type: ignore[import-untyped]
from telethon.tl.functions.contacts import UnblockRequest  # type: ignore[import-untyped]
from telethon.tl.types import Message  # type: ignore[import-untyped]
from aiogram.types import Message as AiogramMessage  # type: ignore[import-untyped]

from .. import loader, utils


@loader.tds
class InlineStuff(loader.Module):
    """Provides support for inline stuff"""

    strings: Callable[[str], str] = {"name": "InlineStuff"}  # type: ignore[assignment]

    @loader.watcher(
        "out",
        "only_inline",
        contains="This message will be deleted automatically",
    )
    async def watcher(self, message: Message):
        if message.via_bot_id == self.inline.bot_id:
            await message.delete()

    @loader.watcher("out", "only_inline", contains="Opening gallery...")
    async def gallery_watcher(self, message: Message):
        if message.via_bot_id != self.inline.bot_id:
            return

        match: Optional[re.Match[str]] = re.search(r"#id: ([a-zA-Z0-9]+)", message.raw_text)
        assert match
        id_ = match[1]

        await message.delete()

        m = await message.respond("🌘", reply_to=utils.get_topic(message))

        await self.inline.gallery(
            message=m,
            next_handler=self.inline._custom_map[id_]["handler"],
            caption=self.inline._custom_map[id_].get("caption", ""),
            force_me=self.inline._custom_map[id_].get("force_me", False),
            disable_security=self.inline._custom_map[id_].get("disable_security", False),
            silent=True,
        )

    async def _check_bot(self, username: str) -> bool:
        async with self._client.conversation("@BotFather", exclusive=False) as conv:
            try:
                await conv.send_message("/token")
            except YouBlockedUserError:
                await self._client(UnblockRequest(id="@BotFather"))
                await conv.send_message("/token")

            r = await conv.get_response()

            if not hasattr(r, "reply_markup") or not hasattr(r.reply_markup, "rows"):
                return False

            for row in r.reply_markup.rows:
                for button in row.buttons:
                    if username != button.text.strip("@"):
                        continue

                    await conv.send_message("/cancel")
                    r = await conv.get_response()  # TODO: why reassign r here???

                    return True

            return False  # TODO: default false?

    async def aiogram_watcher(self, message: AiogramMessage):
        if message.text != "/start":
            return

        await message.answer_photo(
            "https://github.com/hikariatama/assets/raw/master/hikka_banner.png",
            caption=self.strings("this_is_hikka"),
        )

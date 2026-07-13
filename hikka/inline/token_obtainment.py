# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import logging
import re

import pyrogram.errors

from .. import utils
from .._internal import fw_protect
from .types import InlineUnit

logger = logging.getLogger(__name__)


class InlineTokenObtainment(InlineUnit):
    async def _create_bot(self) -> None:
        logger.info("User doesn't have bot, attempting creating new one")
        # TODO: no conversation in pyrogram
        return
        async with self._manager._client.conversation(
            "@BotFather", exclusive=False
        ) as conv:
            await fw_protect()
            m = await conv.send_message("/newbot")
            r = await conv.get_response()

            logger.debug(">> %s", m.text)
            logger.debug("<< %s", r.text)

            if "20" in r.text:
                return False

            await fw_protect()

            db_username = self._manager._db.get("hikka.inline", "custom_bot", None)
            if isinstance(db_username, str):
                username = f"@{db_username.strip('@')}"
                try:
                    await self._manager._client.get_chat(username)
                except ValueError:
                    pass
                else:
                    username = f"@hikka_{utils.rand(6)}_bot"
            else:
                username = f"@hikka_{utils.rand(6)}_bot"

            for msg in [
                f"🌘 Hikkaduwa Userbot of {self._manager._name}"[:64],
                username,
                "/setuserpic",
                username,
            ]:
                await fw_protect()
                m = await conv.send_message(msg)
                r = await conv.get_response()

                logger.debug(">> %s", m.text)
                logger.debug("<< %s", r.text)

                await fw_protect()

            try:
                await fw_protect()
                from .. import main

                m = await conv.send_file(main.BASE_PATH / "assets" / "bot_pfp.png")
                r = await conv.get_response()

                logger.debug(">> <Photo>")
                logger.debug("<< %s", r.text)
            except Exception:
                await fw_protect()
                m = await conv.send_message("/cancel")
                r = await conv.get_response()

                logger.debug(">> %s", m.text)
                logger.debug("<< %s", r.text)

            await fw_protect()

        return await self._assert_token(False)

    async def _assert_token(
        self,
        create_new_if_needed: bool = True,
        revoke_token: bool = False,
    ) -> bool:
        if self._manager._token:
            return True

        logger.info("Bot token not found in db, attempting search in BotFather")

        # TODO: no conversation in pyrogram
        return False

        if not self._manager._db.get(__name__, "no_mute", False):
            await utils.dnd(self._manager._client, "@BotFather", True)
            self._manager._db.set(__name__, "no_mute", True)

        async with self._manager._client.conversation(
            "@BotFather", exclusive=False
        ) as conv:
            try:
                await fw_protect()
                m = await conv.send_message("/token")
            except pyrogram.errors.YouBlockedUser:
                await self._manager._client.unblock_user("@BotFather")
                await fw_protect()
                m = await conv.send_message("/token")

            r = await conv.get_response()

            logger.debug(">> %s", m.text)
            logger.debug("<< %s", r.text)

            await fw_protect()

            if not hasattr(r, "reply_markup") or not hasattr(r.reply_markup, "rows"):
                await conv.cancel_all()

                return await self._create_bot() if create_new_if_needed else False

            for row in r.reply_markup.rows:
                for button in row.buttons:
                    if self._manager._db.get(
                        "hikka.inline", "custom_bot", False
                    ) and self._manager._db.get(
                        "hikka.inline", "custom_bot", False
                    ) != button.text.strip("@"):
                        continue

                    if not self._manager._db.get(
                        "hikka.inline",
                        "custom_bot",
                        False,
                    ) and not re.search(r"@hikka_[0-9a-zA-Z]{6}_bot", button.text):
                        continue

                    await fw_protect()

                    m = await conv.send_message(button.text)
                    r = await conv.get_response()

                    logger.debug(">> %s", m.text)
                    logger.debug("<< %s", r.text)

                    if revoke_token:
                        await fw_protect()

                        m = await conv.send_message("/revoke")
                        r = await conv.get_response()

                        logger.debug(">> %s", m.text)
                        logger.debug("<< %s", r.text)

                        await fw_protect()

                        m = await conv.send_message(button.text)
                        r = await conv.get_response()

                        logger.debug(">> %s", m.text)
                        logger.debug("<< %s", r.text)

                    token = r.text.splitlines()[1]

                    self._manager._db.set("hikka.inline", "bot_token", token)
                    self._manager._token = token

                    await fw_protect()

                    for msg in [
                        "/setinline",
                        button.text,
                        "user@hikka:~$",
                        "/setinlinefeedback",
                        button.text,
                        "Enabled",
                        "/setuserpic",
                        button.text,
                    ]:
                        await fw_protect()
                        m = await conv.send_message(msg)
                        r = await conv.get_response()

                        logger.debug(">> %s", m.text)
                        logger.debug("<< %s", r.text)

                    try:
                        await fw_protect()
                        from .. import main

                        m = await conv.send_file(
                            main.BASE_PATH / "assets" / "bot_pfp.png"
                        )
                        r = await conv.get_response()

                        logger.debug(">> <Photo>")
                        logger.debug("<< %s", r.text)
                    except Exception:
                        await fw_protect()
                        m = await conv.send_message("/cancel")
                        r = await conv.get_response()

                        logger.debug(">> %s", m.text)
                        logger.debug("<< %s", r.text)

                    return True

        return await self._create_bot() if create_new_if_needed else False

    async def _reassert_token(self) -> None:
        is_token_asserted = await self._assert_token(revoke_token=True)
        if not is_token_asserted:
            self.init_complete = False
        else:
            await self._manager.register_manager(ignore_token_checks=True)

    async def _dp_revoke_token(self, already_initialised: bool = True) -> None:
        if already_initialised:
            await self._manager._stop()
            logger.error("Got polling conflict. Attempting token revocation...")

        self._manager._db.set("hikka.inline", "bot_token", None)
        self._manager._token = None
        if already_initialised:
            asyncio.ensure_future(self._reassert_token())
        else:
            await self._reassert_token()

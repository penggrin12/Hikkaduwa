# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import io
import json
import logging
import random
import time
import typing
from typing import Callable, Optional

from telethon.tl import functions  # type: ignore[import-untyped]
from telethon.tl.tlobject import TLRequest  # type: ignore[import-untyped]
from telethon.tl.types import Message  # type: ignore[import-untyped]
from telethon.utils import is_list_like  # type: ignore[import-untyped]

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

GROUPS = [
    "auth",
    "account",
    "users",
    "contacts",
    "messages",
    "updates",
    "photos",
    "upload",
    "help",
    "channels",
    "bots",
    "payments",
    "stickers",
    "phone",
    "langpack",
    "folders",
    "stats",
]


CONSTRUCTORS = {
    (lambda x: x[0].lower() + x[1:])(
        method.__class__.__name__.rsplit("Request", 1)[0]
    ): method.CONSTRUCTOR_ID
    for method in utils.array_sum(
        [
            [method for method in dir(getattr(functions, group)) if isinstance(method, TLRequest)]
            for group in GROUPS
        ]
    )
}


@loader.tds
class APIRatelimiterMod(loader.Module):
    """Helps userbot avoid spamming Telegram API"""

    strings: Callable[[str], str] = {"name": "APILimiter"}  # type: ignore[assignment]

    def __init__(self):
        self._ratelimiter: typing.List[tuple] = []
        self._suspend_until = 0
        self._lock = False
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "time_sample",
                15,
                lambda: self.strings("_cfg_time_sample"),
                validator=loader.validators.Integer(minimum=1),
            ),
            loader.ConfigValue(
                "threshold",
                100,
                lambda: self.strings("_cfg_threshold"),
                validator=loader.validators.Integer(minimum=10),
            ),
            loader.ConfigValue(
                "local_floodwait",
                30,
                lambda: self.strings("_cfg_local_floodwait"),
                validator=loader.validators.Integer(minimum=10, maximum=3600),
            ),
            loader.ConfigValue(
                "forbidden_methods",
                ["joinChannel", "importChatInvite"],
                lambda: self.strings("_cfg_forbidden_methods"),
                validator=loader.validators.MultiChoice(
                    [
                        "sendReaction",
                        "joinChannel",
                        "importChatInvite",
                    ]
                ),
                on_change=lambda: self._client.forbid_constructors(
                    map(
                        lambda x: CONSTRUCTORS[x],
                        self.config["forbidden_constructors"],
                    )
                ),
            ),
        )

    async def client_ready(self):
        asyncio.ensure_future(self._install_protection())

    async def _install_protection(self):
        await asyncio.sleep(30)  # Restart lock
        if hasattr(self._client._call, "_old_call_rewritten"):
            raise loader.SelfUnload("Already installed")

        old_call = self._client._call

        async def new_call(
            sender: "MTProtoSender",  # type: ignore  # noqa: F821
            request: TLRequest,
            ordered: bool = False,
            flood_sleep_threshold: Optional[int] = None,
        ):
            await asyncio.sleep(random.randint(1, 5) / 100)
            req = (request,) if not is_list_like(request) else request
            for r in req:
                if (
                    time.perf_counter() > self._suspend_until
                    and not self.get(
                        "disable_protection",
                        True,
                    )
                    and (
                        r.__module__.rsplit(".", maxsplit=1)[1]
                        in {"messages", "account", "channels"}
                    )
                ):
                    request_name = type(r).__name__
                    self._ratelimiter += [(request_name, time.perf_counter())]

                    self._ratelimiter = list(
                        filter(
                            lambda x: time.perf_counter() - x[1] < int(self.config["time_sample"]),
                            self._ratelimiter,
                        )
                    )

                    if len(self._ratelimiter) > int(self.config["threshold"]) and not self._lock:
                        self._lock = True
                        report = io.BytesIO(
                            json.dumps(
                                self._ratelimiter,
                                indent=4,
                            ).encode()
                        )
                        report.name = "local_fw_report.json"

                        await self.inline.bot.send_document(
                            self.tg_id,
                            report,
                            caption=self.inline.sanitise_text(
                                self.strings("warning").format(
                                    self.config["local_floodwait"],
                                    prefix=utils.escape_html(self.get_prefix()),
                                )
                            ),
                        )

                        # It is intented to use time.sleep instead of asyncio.sleep
                        time.sleep(int(self.config["local_floodwait"]))
                        self._lock = False

            return await old_call(sender, request, ordered, flood_sleep_threshold)

        self._client._call = new_call
        self._client._old_call_rewritten = old_call
        self._client._call._hikka_overwritten = True
        logger.debug("Successfully installed ratelimiter")

    async def on_unload(self):
        if hasattr(self._client, "_old_call_rewritten"):
            self._client._call = self._client._old_call_rewritten
            delattr(self._client, "_old_call_rewritten")
            logger.debug("Successfully uninstalled ratelimiter")

    @loader.command()
    async def suspend_api_protect(self, message: Message):
        if not (args := utils.get_args_raw(message)) or not args.isdigit():
            await utils.answer(message, self.strings("args_invalid"))
            return

        self._suspend_until = time.perf_counter() + int(args)
        await utils.answer(message, self.strings("suspended_for").format(args))

    @loader.command()
    async def api_fw_protection(self, message: Message):
        await self.inline.form(
            message=message,
            text=self.strings("u_sure"),
            reply_markup=[
                {"text": self.strings("btn_no"), "action": "close"},
                {"text": self.strings("btn_yes"), "callback": self._finish},
            ],
        )

    @property
    def _debugger(self):
        return None

    async def _finish(self, call: InlineCall):
        state = self.get("disable_protection", True)
        self.set("disable_protection", not state)
        await call.edit(self.strings("on" if state else "off"))

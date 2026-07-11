# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import logging
import random
import string

import pyrogram
from pyrogram.types import Message

from .. import features, loader, main, utils, version
from .._internal import fw_protect, restart
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

ALL_INVOKES = [
    "flush_loader_cache",
    "flush_cache",
    "reload_core",
    "inspect_cache",
    "inspect_modules",
]


@loader.tds
class HikkaSettingsMod(loader.Module):
    """Advanced settings for Hikka Userbot"""

    strings = {"name": "HikkaSettings"}

    def get_watchers(self) -> tuple:
        return [
            str(watcher.__self__.__class__.strings["name"])
            for watcher in self.allmodules.watchers
            if watcher.__self__.__class__.strings is not None
        ], self._db.get(main.__name__, "disabled_watchers", {})

    async def _uninstall(self, call: InlineCall):
        await call.edit(self.get_string("uninstall"))

        async with self.client.conversation("@BotFather") as conv:
            for msg in [
                "/deletebot",
                f"@{self.inline.bot_username}",
                "Yes, I am totally sure.",
            ]:
                await fw_protect()
                m = await conv.send_message(msg)
                r = await conv.get_response()

                logger.debug(">> %s", m.raw_text)
                logger.debug("<< %s", r.raw_text)

                await fw_protect()

        async for dialog in self.client.iter_dialogs(
            None,
            ignore_migrated=True,
        ):
            if (
                dialog.name
                in {
                    "hikka-logs",
                    "hikka-onload",
                    "hikka-assets",
                    "hikka-backups",
                    "hikka-acc-switcher",
                    "silent-tags",
                }
                and dialog.is_channel
                and (
                    dialog.entity.participants_count == 1
                    or dialog.entity.participants_count == 2
                    and dialog.name in {"hikka-logs", "silent-tags"}
                )
                or (
                    self.client.loader.inline.init_complete
                    and dialog.entity.id == self.client.loader.inline.bot_id
                )
            ):
                await fw_protect()
                await self.client.delete_dialog(dialog.entity)

        await fw_protect()

        folders = await self.client(GetDialogFiltersRequest())

        if any(folder.title == "hikka" for folder in folders):
            folder_id = max(
                folders,
                key=lambda x: x.id,
            ).id
            await fw_protect()
            await self.client(UpdateDialogFilterRequest(id=folder_id))

        for handler in logging.getLogger().handlers:
            handler.setLevel(logging.CRITICAL)

        await fw_protect()

        await self.client.log_out()

        restart()

    async def _uninstall_confirm_step_2(self, call: InlineCall):
        await call.edit(
            self.get_string("deauth_confirm_step2"),
            utils.chunks(
                list(
                    sorted(
                        [
                            {
                                "text": self.get_string("deauth_yes"),
                                "callback": self._uninstall,
                            },
                            *[
                                {
                                    "text": self.get_string(f"deauth_no_{i}"),
                                    "action": "close",
                                }
                                for i in range(1, 4)
                            ],
                        ],
                        key=lambda _: random.random(),
                    )
                ),
                2,
            )
            + [
                [
                    {
                        "text": self.get_string("deauth_cancel"),
                        "action": "close",
                    }
                ]
            ],
        )

    @loader.command()
    async def uninstall_hikka(self, message: Message):
        await self.inline.form(
            self.get_string("deauth_confirm"),
            message,
            [
                {
                    "text": self.get_string("deauth_confirm_btn"),
                    "callback": self._uninstall_confirm_step_2,
                },
                {"text": self.get_string("deauth_cancel"), "action": "close"},
            ],
        )

    @loader.command()
    async def watchers(self, message: Message):
        watchers, disabled_watchers = self.get_watchers()
        watchers = [
            f"♻️ {watcher}"
            for watcher in watchers
            if watcher not in list(disabled_watchers.keys())
        ]
        watchers += [f"💢 {k} {v}" for k, v in disabled_watchers.items()]
        await utils.answer(
            message, self.get_string("watchers").format("\n".join(watchers))
        )

    @loader.command()
    async def watcherbl(self, message: Message):
        if not (args := utils.get_args_raw(message)):
            await utils.answer(message, self.get_string("args"))
            return

        watchers, disabled_watchers = self.get_watchers()

        if args.lower() not in map(lambda x: x.lower(), watchers):
            await utils.answer(message, self.get_string("mod404").format(args))
            return

        args = next((x.lower() == args.lower() for x in watchers), False)

        current_bl = [
            v for k, v in disabled_watchers.items() if k.lower() == args.lower()
        ]
        current_bl = current_bl[0] if current_bl else []

        chat = utils.get_chat_id(message)
        if chat not in current_bl:
            if args in disabled_watchers:
                for k in disabled_watchers:
                    if k.lower() == args.lower():
                        disabled_watchers[k].append(chat)
                        break
            else:
                disabled_watchers[args] = [chat]

            await utils.answer(
                message,
                self.get_string("disabled").format(args) + " <b>in current chat</b>",
            )
        else:
            for k in disabled_watchers.copy():
                if k.lower() == args.lower():
                    disabled_watchers[k].remove(chat)
                    if not disabled_watchers[k]:
                        del disabled_watchers[k]
                    break

            await utils.answer(
                message,
                self.get_string("enabled").format(args) + " <b>in current chat</b>",
            )

        self._db.set(main.__name__, "disabled_watchers", disabled_watchers)

    @loader.command()
    async def watchercmd(self, message: Message):
        if not (args := utils.get_args_raw(message)):
            return await utils.answer(message, self.get_string("args"))

        chats, pm, out, incoming = False, False, False, False

        if "-c" in args:
            args = args.replace("-c", "").replace("  ", " ").strip()
            chats = True

        if "-p" in args:
            args = args.replace("-p", "").replace("  ", " ").strip()
            pm = True

        if "-o" in args:
            args = args.replace("-o", "").replace("  ", " ").strip()
            out = True

        if "-i" in args:
            args = args.replace("-i", "").replace("  ", " ").strip()
            incoming = True

        if chats and pm:
            pm = False
        if out and incoming:
            incoming = False

        watchers, disabled_watchers = self.get_watchers()

        if args.lower() not in [watcher.lower() for watcher in watchers]:
            return await utils.answer(message, self.get_string("mod404").format(args))

        args = [watcher for watcher in watchers if watcher.lower() == args.lower()][0]

        if chats or pm or out or incoming:
            disabled_watchers[args] = [
                *(["only_chats"] if chats else []),
                *(["only_pm"] if pm else []),
                *(["out"] if out else []),
                *(["in"] if incoming else []),
            ]
            self._db.set(main.__name__, "disabled_watchers", disabled_watchers)
            await utils.answer(
                message,
                self.get_string("enabled").format(args)
                + f" (<code>{disabled_watchers[args]}</code>)",
            )
            return

        if args in disabled_watchers and "*" in disabled_watchers[args]:
            await utils.answer(message, self.get_string("enabled").format(args))
            del disabled_watchers[args]
            self._db.set(main.__name__, "disabled_watchers", disabled_watchers)
            return

        disabled_watchers[args] = ["*"]
        self._db.set(main.__name__, "disabled_watchers", disabled_watchers)
        await utils.answer(message, self.get_string("disabled").format(args))

    async def inline__setting(self, call: InlineCall, key: str, state: bool = False):
        if callable(key):
            key()
        else:
            self._db.set(main.__name__, key, state)

        if key == "no_nickname" and state and self.get_prefix() == ".":
            await call.answer(
                self.get_string("nonick_warning"),
                show_alert=True,
            )
        else:
            await call.answer("Configuration value saved!")

        await call.edit(
            self.get_string("inline_settings"),
            reply_markup=self._get_settings_markup(),
        )

    async def inline__update(
        self,
        call: InlineCall,
        confirm_required: bool = False,
    ):
        if confirm_required:
            await call.edit(
                self.get_string("confirm_update"),
                reply_markup=[
                    {"text": "🪂 Update", "callback": self.inline__update},
                    {"text": "🚫 Cancel", "action": "close"},
                ],
            )
            return

        await call.answer("You userbot is being updated...", show_alert=True)
        await call.delete()
        await self.invoke("update", "-f", peer="me")

    async def _remove_core_protection(self, call: InlineCall):
        self._db.set(main.__name__, "remove_core_protection", True)
        await call.edit(self.get_string("core_protection_removed"))

    @loader.command()
    async def remove_core_protection(self, message: Message):
        if self._db.get(main.__name__, "remove_core_protection", False):
            await utils.answer(
                message, self.get_string("core_protection_already_removed")
            )
            return

        await self.inline.form(
            message=message,
            text=self.get_string("core_protection_confirm"),
            reply_markup=[
                {
                    "text": self.get_string("core_protection_btn"),
                    "callback": self._remove_core_protection,
                },
                {
                    "text": self.get_string("btn_no"),
                    "action": "close",
                },
            ],
        )

    async def inline__restart(
        self,
        call: InlineCall,
        confirm_required: bool = False,
    ):
        if confirm_required:
            await call.edit(
                self.get_string("confirm_restart"),
                reply_markup=[
                    {"text": "🔄 Restart", "callback": self.inline__restart},
                    {"text": "🚫 Cancel", "action": "close"},
                ],
            )
            return

        await call.answer("You userbot is being restarted...", show_alert=True)
        await call.delete()
        await self.invoke("restart", "-f", peer="me")

    def _get_settings_markup(self) -> list:
        return [
            [
                (
                    {
                        "text": "✅ NoNick",
                        "callback": self.inline__setting,
                        "args": (
                            "no_nickname",
                            False,
                        ),
                    }
                    if self._db.get(main.__name__, "no_nickname", False)
                    else {
                        "text": "🚫 NoNick",
                        "callback": self.inline__setting,
                        "args": (
                            "no_nickname",
                            True,
                        ),
                    }
                ),
                (
                    {
                        "text": "✅ Grep",
                        "callback": self.inline__setting,
                        "args": (
                            "grep",
                            False,
                        ),
                    }
                    if self._db.get(main.__name__, "grep", False)
                    else {
                        "text": "🚫 Grep",
                        "callback": self.inline__setting,
                        "args": (
                            "grep",
                            True,
                        ),
                    }
                ),
                (
                    {
                        "text": "✅ InlineLogs",
                        "callback": self.inline__setting,
                        "args": (
                            "inlinelogs",
                            False,
                        ),
                    }
                    if self._db.get(main.__name__, "inlinelogs", True)
                    else {
                        "text": "🚫 InlineLogs",
                        "callback": self.inline__setting,
                        "args": (
                            "inlinelogs",
                            True,
                        ),
                    }
                ),
            ],
            [
                (
                    {
                        "text": self.get_string("do_not_suggest_fs"),
                        "callback": self.inline__setting,
                        "args": (
                            "disable_modules_fs",
                            False,
                        ),
                    }
                    if self._db.get(main.__name__, "disable_modules_fs", False)
                    else {
                        "text": self.get_string("suggest_fs"),
                        "callback": self.inline__setting,
                        "args": (
                            "disable_modules_fs",
                            True,
                        ),
                    }
                )
            ],
            [
                (
                    {
                        "text": self.get_string("use_fs"),
                        "callback": self.inline__setting,
                        "args": (
                            "permanent_modules_fs",
                            False,
                        ),
                    }
                    if self._db.get(main.__name__, "permanent_modules_fs", False)
                    else {
                        "text": self.get_string("do_not_use_fs"),
                        "callback": self.inline__setting,
                        "args": (
                            "permanent_modules_fs",
                            True,
                        ),
                    }
                ),
            ],
            [
                (
                    {
                        "text": self.get_string("suggest_subscribe"),
                        "callback": self.inline__setting,
                        "args": (
                            "suggest_subscribe",
                            False,
                        ),
                    }
                    if self._db.get(main.__name__, "suggest_subscribe", True)
                    else {
                        "text": self.get_string("do_not_suggest_subscribe"),
                        "callback": self.inline__setting,
                        "args": (
                            "suggest_subscribe",
                            True,
                        ),
                    }
                ),
            ],
            [
                {
                    "text": self.get_string("btn_restart"),
                    "callback": self.inline__restart,
                    "args": (True,),
                },
                {
                    "text": self.get_string("btn_update"),
                    "callback": self.inline__update,
                    "args": (True,),
                },
            ],
            [
                # kinda hacky
                {
                    "text": self.lookup("HikkaConfig").strings("back_btn"),
                    "callback": self.lookup("HikkaConfig").inline__choose_category,
                },
                {
                    "text": self.lookup("HikkaConfig").strings("close_btn"),
                    "action": "close",
                },
            ],
        ]

    async def inline__settings(
        self,
        call: InlineCall,
    ):
        await call.edit(
            self.get_string("inline_settings"), reply_markup=self._get_settings_markup()
        )
        # await self.inline.form(
        #     self.get_string("inline_settings"),
        #     message=call.message,
        #     reply_markup=self._get_settings_markup(),
        # )

    if features.SETTINGS_AS_COMMAND:

        @loader.command()
        async def settings(self, message: Message):
            await self.inline.form(
                self.get_string("inline_settings"),
                message=message,
                reply_markup=self._get_settings_markup(),
            )

    @loader.loop(interval=1, autostart=True)
    async def loop(self):
        if not (obj := self.allmodules.get_approved_channel):
            return

        channel, event = obj

        try:
            await self.client(JoinChannelRequest(channel))
        except Exception:
            logger.exception("Failed to join channel")
            event.status = False
            event.set()
        else:
            event.status = True
            event.set()

    def _get_all_IDM(self, module: str):
        return {
            getattr(getattr(self.lookup(module), name), "name", name): getattr(
                self.lookup(module), name
            )
            for name in dir(self.lookup(module))
            if getattr(getattr(self.lookup(module), name), "is_debug_method", False)
        }

    @loader.command()
    async def invokecmd(self, message: Message):
        if not (args := utils.get_args_raw(message)) or len(args.split()) < 2:
            await utils.answer(message, self.get_string("no_args"))
            return

        module = args.split()[0]
        method = args.split(maxsplit=1)[1]

        if module != "core" and not self.lookup(module):
            await utils.answer(message, self.get_string("module404").format(module))
            return

        if (
            module == "core"
            and method not in ALL_INVOKES
            or module != "core"
            and method not in self._get_all_IDM(module)
        ):
            await utils.answer(message, self.get_string("invoke404").format(method))
            return

        message = await utils.answer(
            message, self.get_string("invoking").format(method, module)
        )
        result = ""

        if module == "core":
            if method == "flush_loader_cache":
                result = (
                    f"Dropped {await self.lookup('loader').flush_cache()} cache records"
                )
            elif method == "flush_cache":
                result = f"Dropped {self.lookup('loader').flush_cache()} loader links cache records"
                self._client.me = await self._client.get_me()
            elif method == "reload_core":
                core_quantity = await self.lookup("loader").reload_core()
                result = f"Reloaded {core_quantity} core modules"
            elif method == "inspect_cache":
                result = f"Loader links cache: {self.lookup('loader').inspect_cache()} records"
            elif method == "inspect_modules":
                result = (
                    "Loaded modules: {}\nLoaded core modules: {}\nLoaded user modules: {}"
                ).format(
                    len(self.allmodules.modules),
                    sum(
                        module.__origin__.startswith("<core")
                        for module in self.allmodules.modules
                    ),
                    sum(
                        not module.__origin__.startswith("<core")
                        for module in self.allmodules.modules
                    ),
                )
        else:
            result = await self._get_all_IDM(module)[method](message)

        await utils.answer(
            message,
            self.get_string("invoke").format(method, utils.escape_html(result)),
        )

    async def blacklistcommon(self, message: Message):
        args = utils.get_args(message)

        if len(args) > 2:
            await utils.answer(message, self.get_string("too_many_args"))
            return

        chatid = None
        module = None

        if args:
            try:
                chatid = int(args[0])
            except ValueError:
                module = args[0]

        if len(args) == 2:
            module = args[1]

        if chatid is None:
            chatid = utils.get_chat_id(message)

        module = self.allmodules.get_classname(module)
        return f"{str(chatid)}.{module}" if module else chatid

    @loader.command()
    async def hikkacmd(self, message: Message):
        await utils.answer(
            message,
            self.get_string("hikka").format(
                "🌘 <b>Hikkaduwa userbot</b>",
                *version.__version__,
                utils.get_commit_url(),
                utils.get_git_branch() or "Unknown",
                f"{pyrogram.__version__} #{pyrogram.raw.all.layer}",
            ),
        )

    async def getuser(self, message: Message):
        try:
            return int(utils.get_args(message)[0])
        except (ValueError, IndexError):
            if reply := await message.get_reply_message():
                return reply.sender_id

            return message.to_id.user_id if message.is_private else False

    @loader.command()
    async def setprefix(self, message: Message):
        if not (args := utils.get_args_raw(message)):
            await utils.answer(message, self.get_string("what_prefix"))
            return

        if len(args) != 1:
            await utils.answer(message, self.get_string("prefix_incorrect"))
            return

        if args == "s":
            await utils.answer(message, self.get_string("prefix_incorrect"))
            return

        oldprefix = utils.escape_html(self.get_prefix())
        self._db.set(
            main.__name__,
            "command_prefix",
            args,
        )
        await utils.answer(
            message,
            self.get_string("prefix_set").format(
                "👍",
                newprefix=utils.escape_html(args[0]),
                oldprefix=utils.escape_html(oldprefix),
            ),
        )

    @loader.command()
    async def aliases(self, message: Message):
        await utils.answer(
            message,
            self.get_string("aliases")
            + "\n".join(
                [
                    f"▫️ <code>{i}</code> &lt;- {y}"
                    for i, y in self.allmodules.aliases.items()
                ]
            ),
        )

    @loader.command()
    async def addalias(self, message: Message):
        if len(args := utils.get_args(message)) != 2:
            await utils.answer(message, self.get_string("alias_args"))
            return

        alias, cmd = args
        if self.allmodules.add_alias(alias, cmd):
            self.set(
                "aliases",
                {
                    **self.get("aliases", {}),
                    alias: cmd,
                },
            )
            await utils.answer(
                message,
                self.get_string("alias_created").format(utils.escape_html(alias)),
            )
        else:
            await utils.answer(
                message,
                self.get_string("no_command").format(utils.escape_html(cmd)),
            )

    @loader.command()
    async def delalias(self, message: Message):
        args = utils.get_args(message)

        if len(args) != 1:
            await utils.answer(message, self.get_string("delalias_args"))
            return

        alias = args[0]

        if not self.allmodules.remove_alias(alias):
            await utils.answer(
                message,
                self.get_string("no_alias").format(utils.escape_html(alias)),
            )
            return

        current = self.get("aliases", {})
        del current[alias]
        self.set("aliases", current)
        await utils.answer(
            message,
            self.get_string("alias_removed").format(utils.escape_html(alias)),
        )

    @loader.command()
    async def cleardb(self, message: Message):
        await self.inline.form(
            self.get_string("confirm_cleardb"),
            message,
            reply_markup=[
                {
                    "text": self.get_string("cleardb_confirm"),
                    "callback": self._inline__cleardb,
                },
                {
                    "text": self.get_string("cancel"),
                    "action": "close",
                },
            ],
        )

    @loader.command()
    async def ch_hikka_bot(self, message: Message):
        args = utils.get_args_raw(message).strip("@")
        if (
            not args
            or not args.lower().endswith("bot")
            or len(args) <= 4
            or any(
                litera not in (string.ascii_letters + string.digits + "_")
                for litera in args
            )
        ):
            await utils.answer(message, self.get_string("bot_username_invalid"))
            return

        try:
            await self._client.get_entity(f"@{args}")
        except ValueError:
            pass
        else:
            if not await self._check_bot(args):
                await utils.answer(message, self.get_string("bot_username_occupied"))
                return

        self._db.set("hikka.inline", "custom_bot", args)
        self._db.set("hikka.inline", "bot_token", None)
        await utils.answer(message, self.get_string("bot_updated"))

    async def _inline__cleardb(self, call: InlineCall):
        self._db.clear()
        self._db.save()
        await utils.answer(call, self.get_string("db_cleared"))

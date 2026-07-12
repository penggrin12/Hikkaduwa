"""Loads and registers modules"""

# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import ast
import asyncio
import contextlib
import copy
import functools
import importlib
import inspect
import logging
import os
import re
import shutil
import sys
import time
import typing
import uuid
from collections import ChainMap
from importlib.machinery import ModuleSpec
from subprocess import PIPE
from urllib.parse import urlparse

import pyrogram.errors
import requests
from pyrogram.types import Chat, Message

from .. import loader, main, utils
from .._local_storage import RemoteStorage
from ..types import CoreOverwriteError, CoreUnloadError

if typing.TYPE_CHECKING:
    from io import BytesIO

    from ..inline.types import InlineCall
    from ..types import MessageLike

logger = logging.getLogger(__name__)


class FakeLock:
    async def __aenter__(self, *args) -> None:
        pass

    async def __aexit__(self, *args) -> None:
        pass


class FakeNotifier:
    def __enter__(self) -> None:
        pass

    def __exit__(self, *args) -> None:
        pass


@loader.tds
class LoaderMod(loader.Module):
    """Loads modules"""

    strings = {"name": "Loader"}

    def __init__(self) -> None:
        self.fully_loaded = False
        self._links_cache = {}
        self._storage: RemoteStorage | None = None

        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "MODULES_REPO",
                "https://mods.hikariatama.ru",
                lambda: self.get_string("repo_config_doc"),
                validator=loader.validators.Link(),
            ),
            loader.ConfigValue(
                "ADDITIONAL_REPOS",
                # Currently the trusted developers are specified
                [
                    "https://github.com/hikariatama/host/raw/master",
                    "https://github.com/MoriSummerz/ftg-mods/raw/main",
                    "https://gitlab.com/CakesTwix/friendly-userbot-modules/-/raw/master",
                ],
                lambda: self.get_string("add_repo_config_doc"),
                validator=loader.validators.Series(validator=loader.validators.Link()),
            ),
            loader.ConfigValue(
                "share_link",
                doc=lambda: self.get_string("share_link_doc"),
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "basic_auth",
                None,
                lambda: self.get_string("basic_auth_doc"),
                validator=loader.validators.Hidden(
                    loader.validators.RegExp(r"^.*:.*$")
                ),
            ),
        )

    async def _async_init(self):
        # Bloat..?
        modules = list(
            filter(
                lambda x: not x.startswith("https://mods.hikariatama.ru"),
                utils.array_sum(
                    map(
                        lambda x: list(x.values()),
                        (await self.get_repo_list()).values(),
                    )
                ),
            )
        )
        logger.debug("Modules: %s", modules)
        asyncio.ensure_future(self._storage.preload(modules))

    async def client_ready(self):
        # while not (settings := self.lookup("settings")):
        #     await asyncio.sleep(0.5)

        self._storage = RemoteStorage(self.client)

        # self.allmodules.add_aliases(settings.get("aliases", {}))

        main.hikka.ready.set()

        asyncio.ensure_future(self._update_modules())
        # asyncio.ensure_future(self._async_init())

    @loader.loop(interval=3, wait_before=True, autostart=True)
    async def _config_autosaver(self):
        for mod in self.allmodules.modules:
            if (
                not hasattr(mod, "config")
                or not mod.config
                or not isinstance(mod.config, loader.ModuleConfig)
            ):
                continue

            for option, config in mod.config._config.items():
                if not hasattr(config, "_save_marker"):
                    continue

                delattr(mod.config._config[option], "_save_marker")
                mod.pointer("__config__", {})[option] = config.value

        for lib in self.allmodules.libraries:
            if (
                not hasattr(lib, "config")
                or not lib.config
                or not isinstance(lib.config, loader.ModuleConfig)
            ):
                continue

            for option, config in lib.config._config.items():
                if not hasattr(config, "_save_marker"):
                    continue

                delattr(lib.config._config[option], "_save_marker")
                lib._lib_pointer("__config__", {})[option] = config.value

        self._db.save()

    def update_modules_in_db(self) -> None:
        if self.allmodules.secure_boot:
            return

        self.set(
            "loaded_modules",
            {
                **{
                    module.__class__.__name__: module.__origin__
                    for module in self.allmodules.modules
                    if module.__origin__.startswith("http")
                },
            },
        )

    @loader.command(alias="dlm")
    async def dlmod(self, message: Message):
        if args := utils.get_args(message):
            args = args[0]

            await self.download_and_install(args, message)
            if self.fully_loaded:
                self.update_modules_in_db()
        else:
            await self.inline.list(
                message,
                [
                    self.get_string("avail_header")
                    + f"\n☁️ {repo.strip('/')}\n\n"
                    + "\n".join(
                        [
                            " | ".join(chunk)
                            for chunk in utils.chunks(
                                [
                                    f"<code>{i}</code>"
                                    for i in sorted(
                                        [
                                            utils.escape_html(
                                                i.split("/")[-1].split(".")[0]
                                            )
                                            for i in mods.values()
                                        ]
                                    )
                                ],
                                5,
                            )
                        ]
                    )
                    for repo, mods in (await self.get_repo_list()).items()
                ],
            )

    async def _get_modules_to_load(self) -> dict:
        todo = typing.cast(dict, self.get("loaded_modules", {}))
        logger.debug("Loading modules: %s", todo)
        return todo

    async def _get_repo(self, repo: str) -> str:
        repo = repo.strip("/")

        if self._links_cache.get(repo, {}).get("exp", 0) >= time.time():
            return self._links_cache[repo]["data"]

        res = await utils.run_sync(
            requests.get,
            f"{repo}/full.txt",
            auth=(
                tuple(self.config["basic_auth"].split(":", 1))
                if self.config["basic_auth"]
                else None
            ),
        )

        if not str(res.status_code).startswith("2"):
            logger.debug(
                "Can't load repo %s contents because of %s status code",
                repo,
                res.status_code,
            )
            return ""

        self._links_cache[repo] = {
            "exp": time.time() + 5 * 60,
            "data": [link for link in res.text.strip().splitlines() if link],
        }

        return self._links_cache[repo]["data"]

    async def get_repo_list(
        self,
        only_primary: bool = False,
    ) -> dict:
        return {
            repo: {
                f"Mod/{repo_id}/{i}": f"{repo.strip('/')}/{link}.py"
                for i, link in enumerate(set(await self._get_repo(repo)))
            }
            for repo_id, repo in enumerate(
                [self.config["MODULES_REPO"]]
                + ([] if only_primary else self.config["ADDITIONAL_REPOS"])
            )
            if repo.startswith("http")
        }

    async def get_links_list(self) -> list[str]:
        links = await self.get_repo_list()
        main_repo = list(links.pop(self.config["MODULES_REPO"]).values())
        return main_repo + list(dict(ChainMap(*list(links.values()))).values())

    async def _find_link(self, module_name: str) -> str | None:
        return next(
            filter(
                lambda link: link.lower().endswith(f"/{module_name.lower()}.py"),
                await self.get_links_list(),
            ),
            None,
        )

    async def download_and_install(
        self, module_name: str, message: Message | None = None
    ) -> None:
        try:
            blob_link = False
            module_name = module_name.strip()
            if urlparse(module_name).netloc:
                url = module_name
                if re.match(
                    r"^(https:\/\/github\.com\/.*?\/.*?\/blob\/.*\.py)|"
                    r"(https:\/\/gitlab\.com\/.*?\/.*?\/-\/blob\/.*\.py)$",
                    url,
                ):
                    url = url.replace("/blob/", "/raw/")
                    blob_link = True
            else:
                url = await self._find_link(module_name)

                if not url:
                    if message is not None:
                        await utils.answer(message, self.get_string("no_module"))

                    return

            if message:
                message = await utils.answer(
                    message,
                    self.get_string("installing").format(module_name),
                )

            try:
                r = await self._storage.fetch(url, auth=self.config["basic_auth"])
            except requests.exceptions.HTTPError:
                if message is not None:
                    await utils.answer(message, self.get_string("no_module"))

                return

            await self.load_module(
                doc=r,
                message=message,
                name=module_name,
                origin=url,
                blob_link=blob_link,
            )
            return
        except Exception:
            logger.exception("Failed to load %s", module_name)

    async def _inline__load(self, call: "InlineCall", doc: str, mode: str) -> None:
        save = False
        if mode == "all_yes":
            self._db.set(main.__name__, "permanent_modules_fs", True)
            self._db.set(main.__name__, "disable_modules_fs", False)
            await call.answer(self.get_string("will_save_fs"))
            save = True
        elif mode == "all_no":
            self._db.set(main.__name__, "disable_modules_fs", True)
            self._db.set(main.__name__, "permanent_modules_fs", False)
        elif mode == "once":
            save = True

        await self.load_module(doc=doc, message=call, save_fs=save)

    @loader.command(alias="lm")
    async def loadmod(self, message: Message) -> None:
        force_save: bool = "-fs" in utils.get_args_raw(message)

        msg = message if message.document else message.reply_to_message
        if msg is None or msg.document is None:
            await utils.answer(message, self.get_string("provide_module"))
            return

        file: "BytesIO" = await msg.download(in_memory=True)  # type: ignore

        logger.debug("Loading external module...")

        try:
            doc: str = file.getvalue().decode(encoding="utf-8")
        except UnicodeDecodeError:
            await utils.answer(message, self.get_string("bad_unicode"))
            return

        if (
            not self._db.get(
                main.__name__,
                "disable_modules_fs",
                False,
            )
            and not self._db.get(main.__name__, "permanent_modules_fs", False)
            and not force_save
        ):
            if message.id == msg.id:
                if utils.can_edit(msg):
                    await msg.edit_caption(caption="")
                msg = await message.answer(text="🌘")
            else:
                msg = message

            if await self.inline.form(
                self.get_string("module_fs"),
                message=msg,
                reply_markup=[
                    [
                        {
                            "text": self.get_string("save"),
                            "callback": self._inline__load,
                            "args": (doc, "once"),
                        },
                        {
                            "text": self.get_string("no_save"),
                            "callback": self._inline__load,
                            "args": (doc, "no"),
                        },
                    ],
                    [
                        {
                            "text": self.get_string("save_for_all"),
                            "callback": self._inline__load,
                            "args": (doc, "all_yes"),
                        }
                    ],
                    [
                        {
                            "text": self.get_string("never_save"),
                            "callback": self._inline__load,
                            "args": (doc, "all_no"),
                        }
                    ],
                ],
            ):
                return

        await self.load_module(
            doc=doc,
            message=msg,
            save_fs=(
                force_save
                or bool(self._db.get(main.__name__, "permanent_modules_fs", False))
                and not bool(self._db.get(main.__name__, "disable_modules_fs", False))
            ),
        )

    async def load_module(
        self,
        doc: str,
        message: "MessageLike | None",
        name: str | None = None,
        origin: str = "<string>",
        did_requirements: bool = False,
        save_fs: bool = False,
        blob_link: bool = False,
    ) -> None:
        if any(
            line.replace(" ", "") == "#scope:ffmpeg" for line in doc.splitlines()
        ) and (not utils.is_ffmpeg_installed()):
            if isinstance(message, Message):
                await utils.answer(message, self.get_string("ffmpeg_required"))
            return

        if (
            any(line.replace(" ", "") == "#scope:inline" for line in doc.splitlines())
            and not self.inline.init_complete
        ):
            if isinstance(message, Message):
                await utils.answer(message, self.get_string("inline_init_failed"))
            return

        if re.search(r"# ?scope: ?hikka_min", doc):
            ver = re.search(r"# ?scope: ?hikka_min ((?:\d+\.){2}\d+)", doc).group(1)
            ver_ = tuple(map(int, ver.split(".")))
            if main.__version__ < ver_:
                if isinstance(message, Message):
                    if getattr(message, "file", None):
                        m = utils.get_chat_id_keep_minus100(message)
                        await message.edit("")
                    else:
                        m = message

                    await self.inline.form(
                        self.get_string("version_incompatible").format(ver),
                        m,
                        reply_markup=[
                            {
                                "text": self.lookup("updater").strings("btn_update"),
                                "callback": self.lookup("updater").inline_update,
                            },
                            {
                                "text": self.lookup("updater").strings("cancel"),
                                "action": "close",
                            },
                        ],
                    )
                return

        developer = re.search(r"# ?meta developer: ?(.+)", doc)
        developer = developer.group(1) if developer else False

        blob_link = self.get_string("blob_link") if blob_link else ""

        if (name is not None) and utils.check_url(name):
            url = copy.deepcopy(name)
        elif utils.check_url(origin):
            url = copy.deepcopy(origin)
        else:
            url = None

        if name is None:
            try:
                node = ast.parse(doc)
                uid = next(
                    n.name
                    for n in node.body
                    if isinstance(n, ast.ClassDef)
                    and any(
                        isinstance(base, ast.Attribute)
                        and base.value.id == "Module"
                        or isinstance(base, ast.Name)
                        and base.id == "Module"
                        for base in n.bases
                    )
                )
            except Exception:
                logger.debug(
                    "Can't parse classname from code, using legacy uid instead",
                    exc_info=True,
                )
                uid = "__extmod_" + str(uuid.uuid4())
        else:
            if name.startswith(self.config["MODULES_REPO"]):
                name = name.split("/")[-1].split(".py")[0]

            uid = name.replace("%", "%%").replace(".", "%d")

        module_name = f"hikka.modules.{uid}"

        async def core_overwrite(e: CoreOverwriteError):
            nonlocal message

            with contextlib.suppress(Exception):
                self.allmodules.modules.remove(instance)

            if not message:
                return

            await utils.answer(
                message,
                self.get_string(f"overwrite_{e.type}").format(
                    *(
                        (e.target,)
                        if e.type == "module"
                        else (utils.escape_html(self.get_prefix()), e.target)
                    )
                ),
            )

        # TODO: do we need this lock and notifier?
        try:
            try:
                spec = ModuleSpec(
                    module_name,
                    loader.StringLoader(doc, f"<external {module_name}>"),
                    origin=f"<external {module_name}>",
                )
                instance = await self.allmodules.register_module(
                    spec,
                    module_name,
                    origin,
                    save_fs=save_fs,
                )

            except ImportError as e:
                logger.info(
                    "Module loading failed, attempting dependency installation (%s)",
                    e.name,
                )
                # Let's try to reinstall dependencies
                try:
                    requirements = list(
                        filter(
                            lambda x: not x.startswith(("-", "_", ".")),
                            map(
                                str.strip,
                                loader.VALID_PIP_PACKAGES.search(doc)[1].split(),
                            ),
                        )
                    )
                except TypeError:
                    logger.warning(
                        "No valid pip packages specified in code, attempting installation from error"
                    )
                    requirements = [
                        {
                            "sklearn": "scikit-learn",
                            "pil": "Pillow",
                            "pyrogram": "kurigram",
                        }.get(e.name.lower(), e.name)
                    ]

                if not requirements:
                    raise Exception("Nothing to install") from e

                logger.debug("Installing requirements: %s", requirements)

                if did_requirements:
                    if message is not None:
                        await utils.answer(
                            message,
                            self.get_string("requirements_restart").format(e.name),
                        )

                    return

                if message is not None:
                    await utils.answer(
                        message,
                        self.get_string("requirements_installing").format(
                            "\n".join(f"▫️ {req}" for req in requirements)
                        ),
                    )

                pip = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "-q",
                    "--disable-pip-version-check",
                    "--no-warn-script-location",
                    *["--user"] if loader.USER_INSTALL else [],
                    *requirements,
                    stderr=PIPE,
                )

                rc = await pip.wait()

                if rc != 0:
                    logger.error((await pip.stderr.read()).decode("utf-8"))

                    if message is not None:
                        if "com.termux" in os.environ.get("PREFIX", ""):
                            await utils.answer(
                                message,
                                self.get_string("requirements_failed_termux"),
                            )
                        else:
                            await utils.answer(
                                message,
                                self.get_string("requirements_failed"),
                            )

                    return

                importlib.invalidate_caches()

                kwargs = utils.get_kwargs()
                kwargs["did_requirements"] = True

                await self.load_module(**kwargs)  # Try again
                return
            except CoreOverwriteError as e:
                await core_overwrite(e)
                return
            except loader.LoadError as e:
                with contextlib.suppress(Exception):
                    await self.allmodules.unload_module(instance.__class__.__name__)

                with contextlib.suppress(Exception):
                    self.allmodules.modules.remove(instance)

                if message:
                    await utils.answer(
                        message,
                        f"😖 <b>{utils.escape_html(str(e))}</b>",
                    )
                return
        except Exception as e:
            logger.exception("Loading external module failed due to %s", e)

            if message is not None:
                await utils.answer(message, self.get_string("load_failed"))

            return

        if hasattr(instance, "__version__") and isinstance(instance.__version__, tuple):
            version = f"<b><i> (v{'.'.join(list(map(str, list(instance.__version__))))})</i></b>"
        else:
            version = ""

        try:
            try:
                self.allmodules.send_config_one(instance)

                async def inner_proxy() -> None:
                    nonlocal instance, message
                    while True:
                        if hasattr(instance, "hikka_wait_channel_approve"):
                            if message:
                                (
                                    module,
                                    channel,
                                    reason,
                                ) = instance.hikka_wait_channel_approve
                                message = await utils.answer(
                                    message,
                                    self.get_string("wait_channel_approve").format(
                                        module,
                                        channel.username,
                                        utils.escape_html(channel.title),
                                        utils.escape_html(reason),
                                        self.inline.bot_username,
                                    ),
                                )
                                return

                        await asyncio.sleep(0.1)

                task = asyncio.ensure_future(inner_proxy())
                await self.allmodules.send_ready_one(
                    instance,
                    no_self_unload=True,
                    from_dlmod=bool(message),
                )
                task.cancel()
            except CoreOverwriteError as e:
                await core_overwrite(e)
                return
            except (loader.LoadError, loader.SelfUnload) as e:
                if isinstance(e, loader.SelfUnload):
                    logger.debug(
                        "Unloading %s, because it raised `SelfUnload`", instance
                    )

                with contextlib.suppress(Exception):
                    await self.allmodules.unload_module(instance.__class__.__name__)

                with contextlib.suppress(Exception):
                    self.allmodules.modules.remove(instance)

                if message:
                    await utils.answer(
                        message,
                        f"😖 <b>{utils.escape_html(str(e))}</b>",
                    )
                return
            except loader.SelfSuspend as e:
                logger.debug("Suspending %s, because it raised `SelfSuspend`", instance)
                if message:
                    await utils.answer(
                        message,
                        (
                            f"🥶 <b>Module suspended itself\nReason: {utils.escape_html(str(e))}</b>"
                        ),
                    )
                return
        except Exception as e:
            logger.exception("Module threw because of %s", e)

            if message is not None:
                await utils.answer(message, self.get_string("load_failed"))

            return

        instance.hikka_meta_pic = next(
            (
                line.replace(" ", "").split("#metapic:", maxsplit=1)[1]
                for line in doc.splitlines()
                if line.replace(" ", "").startswith("#metapic:")
            ),
            None,
        )

        pack_url = next(
            (
                line.replace(" ", "").split("#packurl:", maxsplit=1)[1]
                for line in doc.splitlines()
                if line.replace(" ", "").startswith("#packurl:")
            ),
            None,
        )

        if pack_url and (
            translations := await self.allmodules.translator.load_module_translations(
                pack_url
            )
        ):
            instance.strings.external_strings = translations

        for alias, cmd in self.lookup("HikkaSettings").get("aliases", {}).items():
            if cmd in instance.commands:
                self.allmodules.add_alias(alias, cmd)

        try:
            modname = instance.strings("name")
        except (KeyError, AttributeError):
            modname = getattr(instance, "name", instance.__class__.__name__)

        try:
            developer_entity = await (
                self.client.force_get_entity
                if (
                    developer in self.client.hikka_entity_cache
                    and getattr(
                        await self.client.get_entity(developer),
                        "left",
                        True,
                    )
                )
                else self.client.get_entity
            )(developer)
        except Exception:
            developer_entity = None

        if not isinstance(developer_entity, Chat):
            developer_entity = None

        if message is None:
            return

        modhelp = ""

        if instance.__doc__:
            modhelp += (
                f"<i>\nℹ️ {utils.escape_html(inspect.getdoc(instance) or '')}</i>\n"
            )

        subscribe = ""
        subscribe_markup = None

        depends_from = []
        for key in dir(instance):
            value = getattr(instance, key)
            if isinstance(value, loader.Library):
                depends_from.append(
                    "▫️ <code>{}</code> <b>{}</b> <code>{}</code>".format(
                        value.__class__.__name__,
                        self.get_string("by"),
                        (
                            value.developer
                            if isinstance(getattr(value, "developer", None), str)
                            else "Unknown"
                        ),
                    )
                )

        depends_from = (
            self.get_string("depends_from").format("\n".join(depends_from))
            if depends_from
            else ""
        )

        def loaded_msg(use_subscribe: bool = True):
            nonlocal \
                modname, \
                version, \
                modhelp, \
                developer, \
                origin, \
                subscribe, \
                blob_link, \
                depends_from
            return self.get_string("loaded").format(
                modname.strip(),
                version,
                utils.ascii_face(),
                modhelp,
                developer if not subscribe or not use_subscribe else "",
                depends_from,
                (
                    self.get_string("modlink").format(origin)
                    if origin != "<string>" and self.config["share_link"]
                    else ""
                ),
                blob_link,
                subscribe if use_subscribe else "",
            )

        if developer:
            if developer.startswith("@") and developer not in self.get(
                "do_not_subscribe", []
            ):
                if (
                    developer_entity
                    and getattr(developer_entity, "left", True)
                    and self._db.get(main.__name__, "suggest_subscribe", True)
                ):
                    subscribe = self.get_string("suggest_subscribe").format(
                        f"@{utils.escape_html(str(developer_entity.username))}"
                    )
                    subscribe_markup = [
                        {
                            "text": self.get_string("subscribe"),
                            "callback": self._inline__subscribe,
                            "args": (
                                developer_entity.id,
                                functools.partial(loaded_msg, use_subscribe=False),
                                True,
                            ),
                        },
                        {
                            "text": self.get_string("no_subscribe"),
                            "callback": self._inline__subscribe,
                            "args": (
                                developer,
                                functools.partial(loaded_msg, use_subscribe=False),
                                False,
                            ),
                        },
                    ]

            developer = self.get_string("developer").format(
                utils.escape_html(str(developer))
                if isinstance(developer_entity, Chat)
                else f"<code>{utils.escape_html(str(developer))}</code>"
            )
        else:
            developer = ""

        if any(
            line.replace(" ", "") == "#scope:disable_onload_docs"
            for line in doc.splitlines()
        ):
            await utils.answer(message, loaded_msg(), reply_markup=subscribe_markup)
            return

        for _name, fun in sorted(
            instance.commands.items(),
            key=lambda x: x[0],
        ):
            modhelp += "\n{} <code>{}{}</code> {}".format(
                "▫️",
                utils.escape_html(self.get_prefix()),
                _name,
                (
                    utils.escape_html(inspect.getdoc(fun) or "")
                    or self.get_string("undoc")
                ),
            )

        if self.inline.init_complete:
            for _name, fun in sorted(
                instance.inline_handlers.items(),
                key=lambda x: x[0],
            ):
                modhelp += self.get_string("ihandler").format(
                    f"@{self.inline.bot_username} {_name}",
                    (
                        utils.escape_html(inspect.getdoc(fun) or "")
                        if fun.__doc__
                        else self.get_string("undoc")
                    ),
                )

        try:
            await utils.answer(message, loaded_msg(), reply_markup=subscribe_markup)
        except pyrogram.errors.MediaCaptionTooLong:
            await message.reply(loaded_msg(False))

    async def _inline__subscribe(
        self,
        call: "InlineCall",
        entity: int,
        msg: typing.Callable[[], str],
        subscribe: bool,
    ):
        if not subscribe:
            self.set("do_not_subscribe", self.get("do_not_subscribe", []) + [entity])
            await utils.answer(call, msg())
            await call.answer(self.get_string("not_subscribed"))
            return

        await self.client.join_chat(chat_id=entity)
        await utils.answer(call, msg())
        await call.answer(self.get_string("subscribed"))

    @loader.command(alias="ulm")
    async def unloadmod(self, message: Message):
        if not (args := utils.get_args_raw(message)):
            await utils.answer(message, self.get_string("no_class"))
            return

        instance = self.lookup(args)

        if issubclass(instance.__class__, loader.Library):
            await utils.answer(message, self.get_string("cannot_unload_lib"))
            return

        try:
            worked = await self.allmodules.unload_module(args)
        except CoreUnloadError as e:
            await utils.answer(
                message,
                self.get_string("unload_core").format(e.module),
            )
            return

        if not self.allmodules.secure_boot:
            self.set(
                "loaded_modules",
                {
                    mod: link
                    for mod, link in self.get("loaded_modules", {}).items()
                    if mod not in worked
                },
            )

        msg = (
            self.get_string("unloaded").format(
                "✅",
                ", ".join(
                    [(mod[:-3] if mod.endswith("Mod") else mod) for mod in worked]
                ),
            )
            if worked
            else self.get_string("not_unloaded")
        )

        await utils.answer(message, msg)

    @loader.command()
    async def clearmodules(self, message: Message):
        await self.inline.form(
            self.get_string("confirm_clearmodules"),
            message,
            reply_markup=[
                {
                    "text": self.get_string("clearmodules"),
                    "callback": self._inline__clearmodules,
                },
                {
                    "text": self.get_string("cancel"),
                    "action": "close",
                },
            ],
        )

    @loader.command()
    async def addrepo(self, message: Message):
        if not (args := utils.get_args_raw(message)) or (
            not utils.check_url(args) and not utils.check_url(f"https://{args}")
        ):
            await utils.answer(message, self.get_string("no_repo"))
            return

        if args.endswith("/"):
            args = args[:-1]

        if not args.startswith("https://") and not args.startswith("http://"):
            args = f"https://{args}"

        try:
            r = await utils.run_sync(
                requests.get,
                f"{args}/full.txt",
                auth=(
                    tuple(self.config["basic_auth"].split(":", 1))
                    if self.config["basic_auth"]
                    else None
                ),
            )
            r.raise_for_status()
            if not r.text.strip():
                raise ValueError
        except Exception:
            await utils.answer(message, self.get_string("no_repo"))
            return

        if args in self.config["ADDITIONAL_REPOS"]:
            await utils.answer(message, self.get_string("repo_exists").format(args))
            return

        self.config["ADDITIONAL_REPOS"] += [args]

        await utils.answer(message, self.get_string("repo_added").format(args))

    @loader.command()
    async def delrepo(self, message: Message):
        if not (args := utils.get_args_raw(message)) or not utils.check_url(args):
            await utils.answer(message, self.get_string("no_repo"))
            return

        if args.endswith("/"):
            args = args[:-1]

        if args not in self.config["ADDITIONAL_REPOS"]:
            await utils.answer(message, self.get_string("repo_not_exists"))
            return

        self.config["ADDITIONAL_REPOS"].remove(args)

        await utils.answer(message, self.get_string("repo_deleted").format(args))

    async def _inline__clearmodules(self, call: "InlineCall"):
        self.set("loaded_modules", {})

        for file in os.scandir(loader.LOADED_MODULES_DIR):
            try:
                shutil.rmtree(file.path)
            except Exception:
                logger.debug("Failed to remove %s", file.path, exc_info=True)

        await utils.answer(call, self.get_string("all_modules_deleted"))
        await self.lookup("Updater").restart_common(call)

    async def _update_modules(self):
        todo = await self._get_modules_to_load()

        self._secure_boot = False

        if self._db.get(loader.__name__, "secure_boot", False):
            self._db.set(loader.__name__, "secure_boot", False)
            self._secure_boot = True
        else:
            for mod in todo.values():
                await self.download_and_install(mod)

            self.update_modules_in_db()

            # aliases = {
            #     alias: cmd
            #     for alias, cmd in self.lookup("settings").get("aliases", {}).items()
            #     if self.allmodules.add_alias(alias, cmd)
            # }

            # self.lookup("settings").set("aliases", aliases)

        self.fully_loaded = True

        with contextlib.suppress(AttributeError):
            await self.lookup("Updater").full_restart_complete(self._secure_boot)

    def flush_cache(self) -> int:
        """Flush the cache of links to modules"""
        count = sum(map(len, self._links_cache.values()))
        self._links_cache = {}
        return count

    def inspect_cache(self) -> int:
        """Inspect the cache of links to modules"""
        return sum(map(len, self._links_cache.values()))

    async def reload_core(self) -> int:
        """Forcefully reload all core modules"""
        self.fully_loaded = False

        if self._secure_boot:
            self._db.set(loader.__name__, "secure_boot", True)

        if not self._db.get(main.__name__, "remove_core_protection", False):
            for module in self.allmodules.modules:
                if module.__origin__.startswith("<core"):
                    module.__origin__ = "<reload-core>"

        loaded = await self.allmodules.register_all(no_external=True)
        for instance in loaded:
            self.allmodules.send_config_one(instance)
            await self.allmodules.send_ready_one(
                instance,
                no_self_unload=False,
                from_dlmod=False,
            )

        self.fully_loaded = True
        return len(loaded)

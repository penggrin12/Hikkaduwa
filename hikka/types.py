# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html


import ast
import asyncio
import contextlib
import copy
import importlib
import importlib.machinery
import importlib.util
import inspect
import logging
import os
import re
import sys
import typing
from dataclasses import dataclass, field
from importlib.abc import SourceLoader

import pyrogram
import requests
from pyrogram.types import Message

from . import version
from ._reference_finder import replace_all_refs
from .inline.types import (
    BotInlineCall,
    BotInlineMessage,
    BotMessage,
    InlineCall,
    InlineMessage,
    InlineQuery,
    InlineUnit,
)
from .pointers import PointerDict, PointerList

if typing.TYPE_CHECKING:
    from hikka.translations import Strings

    from .client import HikkaClient
    from .hints import EntityLike
    from .loader import Modules

__all__ = [
    "JSONSerializable",
    "HikkaReplyMarkup",
    "ListLike",
    "Command",
    "StringLoader",
    "Module",
    "get_commands",
    "get_inline_handlers",
    "get_callback_handlers",
    "BotInlineCall",
    "BotMessage",
    "InlineCall",
    "InlineMessage",
    "InlineQuery",
    "InlineUnit",
    "BotInlineMessage",
    "PointerDict",
    "PointerList",
]

logger = logging.getLogger(__name__)


JSONSerializable = str | int | float | bool | list | dict | None
HikkaReplyMarkup = list[list[dict]] | list[dict] | dict
ListLike = list | set | tuple
Command = typing.Callable[..., typing.Awaitable[typing.Any]]
MessageLike = Message | InlineCall | InlineMessage

CommandP = typing.ParamSpec("CommandP")
CommandT = typing.Callable[CommandP, typing.Awaitable[None]]


class StringLoader(SourceLoader):
    """Load a python module/file from a string"""

    def __init__(self, data: str, origin: str):
        self.data = data.encode("utf-8") if isinstance(data, str) else data
        self.origin = origin

    def get_source(self, _=None) -> str:
        return self.data.decode("utf-8")

    def get_code(self, fullname: str) -> bytes:
        return (
            compile(source, self.origin, "exec", dont_inherit=True)
            if (source := self.get_data(fullname))
            else None
        )

    def get_filename(self, *args, **kwargs) -> str:
        return self.origin

    def get_data(self, *args, **kwargs) -> bytes:
        return self.data


class Module:
    if typing.TYPE_CHECKING:
        allmodules: "Modules"
        get_string: "Strings"

    strings = {"name": "Unknown"}

    """There is no help for this module"""

    # can also have `reload_dynamic_translate=True`
    def config_complete(self) -> None:
        """Called when module.config is populated"""

    # can also have `client` and `db` positional parameters
    async def client_ready(self) -> None:
        """Called after client is ready (after config_loaded)"""

    def internal_init(self) -> None:
        """Called after the class is initialized in order to pass the client and db. Do not call it yourself"""
        self.db = self.allmodules.db
        self._db = self.allmodules.db
        self.client: "HikkaClient" = self.allmodules.client
        self._client: "HikkaClient" = self.allmodules.client
        self.lookup = self.allmodules.lookup
        self.get_prefix = self.allmodules.get_prefix
        self.inline = self.allmodules.inline
        self.tg_id = self._client.tg_id
        self._tg_id = self._client.tg_id

    async def on_unload(self) -> None:
        """Called after unloading / reloading module"""

    # can also have `client` and `db` positional parameters
    async def on_dlmod(self) -> None:
        """
        Called after the module is first time loaded with .dlmod or .loadmod

        Possible use-cases:
        - Send reaction to author's channel message
        - Create asset folder
        - ...

        ⚠️ Note, that any error there will not interrupt module load, and will just
        send a message to logs with verbosity INFO and exception traceback
        """

    async def invoke(
        self,
        command: str,
        args: str | None = None,
        peer: "EntityLike | None" = None,
        message: Message | None = None,
        edit: bool = False,
    ) -> Message:
        """
        Invoke another command
        :param command: Command to invoke
        :param args: Arguments to pass to command
        :param peer: Peer to send the command to. If not specified, will send to the current chat
        :param edit: Whether to edit the message
        :returns Message:
        """
        if command not in self.allmodules.commands:
            raise ValueError(f"Command {command} not found")

        if not message and not peer:
            raise ValueError("Either peer or message must be specified")

        cmd = f"{self.get_prefix()}{command} {args or ''}".strip()

        message = (
            (await self._client.send_message(peer, cmd))
            if peer
            else (await (message.edit if edit else message.respond)(cmd))
        )
        await self.allmodules.commands[command](message)
        return message

    @property
    def commands(self) -> dict[str, Command]:
        """List of commands that module supports"""
        return get_commands(self)

    @property
    def hikka_commands(self) -> dict[str, Command]:
        """List of commands that module supports"""
        return get_commands(self)

    @property
    def inline_handlers(self) -> dict[str, Command]:
        """List of inline handlers that module supports"""
        return get_inline_handlers(self)

    @property
    def hikka_inline_handlers(self) -> dict[str, Command]:
        """List of inline handlers that module supports"""
        return get_inline_handlers(self)

    @property
    def callback_handlers(self) -> dict[str, Command]:
        """List of callback handlers that module supports"""
        return get_callback_handlers(self)

    @property
    def hikka_callback_handlers(self) -> dict[str, Command]:
        """List of callback handlers that module supports"""
        return get_callback_handlers(self)

    @property
    def watchers(self) -> dict[str, Command]:
        """List of watchers that module supports"""
        return get_watchers(self)

    @property
    def hikka_watchers(self) -> dict[str, Command]:
        """List of watchers that module supports"""
        return get_watchers(self)

    @commands.setter
    def commands(self, _) -> None:
        pass

    @hikka_commands.setter
    def hikka_commands(self, _) -> None:
        pass

    @inline_handlers.setter
    def inline_handlers(self, _) -> None:
        pass

    @hikka_inline_handlers.setter
    def hikka_inline_handlers(self, _) -> None:
        pass

    @callback_handlers.setter
    def callback_handlers(self, _) -> None:
        pass

    @hikka_callback_handlers.setter
    def hikka_callback_handlers(self, _) -> None:
        pass

    @watchers.setter
    def watchers(self, _) -> None:
        pass

    @hikka_watchers.setter
    def hikka_watchers(self, _) -> None:
        pass

    async def animate(
        self,
        message: Message | InlineMessage,
        frames: list[str],
        interval: float | int,
        *,
        inline: bool = False,
    ) -> None:
        """
        Animate message
        :param message: Message to animate
        :param frames: A List of strings which are the frames of animation
        :param interval: Animation delay
        :param inline: Whether to use inline bot for animation
        :returns message:

        Please, note that if you set `inline=True`, first frame will be shown with an empty
        button due to the limitations of Telegram API
        """
        from . import utils

        with contextlib.suppress(AttributeError):
            _hikka_client_id_logging_tag = copy.copy(self.client.tg_id)  # noqa: F841

        if interval < 0.1:
            logger.warning(
                "Resetting animation interval to 0.1s, because it may get you in"
                " floodwaits"
            )
            interval = 0.1

        for frame in frames:
            if isinstance(message, Message):
                if inline:
                    message = await self.inline.form(
                        message=message,
                        text=frame,
                        reply_markup={"text": "\u0020\u2800", "data": "empty"},
                    )
                else:
                    message = await utils.answer(message, frame)
            elif isinstance(message, InlineMessage) and inline:
                await message.edit(frame)

            await asyncio.sleep(interval)

        return message

    def get(
        self,
        key: str,
        default: JSONSerializable | None = None,
    ) -> JSONSerializable:
        return self._db.get(self.__class__.__name__, key, default)

    def set(self, key: str, value: JSONSerializable) -> bool:
        self._db.set(self.__class__.__name__, key, value)

    def pointer(
        self,
        key: str,
        default: JSONSerializable | None = None,
        item_type: typing.Any | None = None,
    ) -> JSONSerializable | PointerList | PointerDict:
        return self._db.pointer(self.__class__.__name__, key, default, item_type)

    async def _approve(
        self,
        call: InlineCall,
        channel: "EntityLike",
        event: asyncio.Event,
    ):
        from . import utils

        local_event = asyncio.Event()
        self.__approve += [(channel, local_event)]  # skipcq: PTC-W0037
        await local_event.wait()
        event.status = local_event.status
        event.set()
        await call.edit(
            (
                "💫 <b>Joined <a"
                f' href="https://t.me/{channel.username}">{utils.escape_html(channel.title)}</a></b>'
            ),
            gif="https://static.hikari.gay/0d32cbaa959e755ac8eef610f01ba0bd.gif",
        )

    async def _decline(
        self,
        call: InlineCall,
        channel: "EntityLike",
        event: asyncio.Event,
    ):
        from . import utils

        self._db.set(
            "hikka.main",
            "declined_joins",
            list(set(self._db.get("hikka.main", "declined_joins", []) + [channel.id])),
        )
        event.status = False
        event.set()
        await call.edit(
            (
                "✖️ <b>Declined joining <a"
                f' href="https://t.me/{channel.username}">{utils.escape_html(channel.title)}</a></b>'
            ),
            gif="https://data.whicdn.com/images/324445359/original.gif",
        )

    async def request_join(
        self,
        peer: "EntityLike",
        reason: str,
        assure_joined: bool | None = False,
    ) -> bool:
        """
        Request to join a channel.
        :param peer: The channel to join.
        :param reason: The reason for joining.
        :param assure_joined: If set, module will not be loaded unless the required channel is joined.
                              ⚠️ Works only in `client_ready`!
                              ⚠️ If user declines to join channel, he will not be asked to
                              join again, so unless he joins it manually, module will not be loaded
                              ever.
        :return: Status of the request.
        :rtype: bool
        :notice: This method will block module loading until the request is approved or declined.
        """
        from . import utils

        event = asyncio.Event()
        await self.client.update_chat_notifications(
            self.inline.bot_username, mute=False, show_previews=False
        )

        if not isinstance(peer, (int, str)):
            raise TypeError("`peer` field must be an ID or a username")

        channel = await self.client.get_chat(peer)
        if channel.id in self._db.get("hikka.main", "declined_joins", []):
            if assure_joined:
                raise LoadError(
                    f"You need to join @{channel.username} in order to use this module"
                )

            return False

        if channel.type != pyrogram.enums.ChatType.CHANNEL:
            raise TypeError("`peer` field must be a channel")

        # if getattr(channel, "left", True):
        #     channel = await self.client.force_get_entity(peer)

        # if not getattr(channel, "left", True):
        #     return True

        await self.inline.bot.send_animation(
            self.tg_id,
            "https://i.gifer.com/SD5S.gif",
            caption=(
                f"💫 <b>Module</b> <code>{self.__class__.__name__}</code>"
                f" <b>requested to join channel <a href='https://t.me/{channel.username}'>{utils.escape_html(channel.title or '?')}</a></b>"
                f"\n\n<b>❓ Reason:</b> <i>{utils.escape_html(reason)}</i>"
            ),
            reply_markup=self.inline.generate_markup(
                [
                    {
                        "text": "💫 Approve",
                        "callback": self._approve,
                        "args": (channel, event),
                    },
                    {
                        "text": "✖️ Decline",
                        "callback": self._decline,
                        "args": (channel, event),
                    },
                ]
            ),
        )

        self.hikka_wait_channel_approve = (
            self.__class__.__name__,
            channel,
            reason,
        )
        await event.wait()

        with contextlib.suppress(AttributeError):
            delattr(self, "hikka_wait_channel_approve")

        if assure_joined and not event.is_set():
            raise LoadError(
                f"You need to join @{channel.username} in order to use this module"
            )

        return event.is_set()

    async def import_lib(
        self,
        url: str,
        *,
        suspend_on_error: bool | None = False,
        _did_requirements: bool = False,
    ) -> "Library":
        """
        Import library from url and register it in :obj:`Modules`
        :param url: Url to import
        :param suspend_on_error: Will raise :obj:`loader.SelfSuspend` if library can't be loaded
        :return: :obj:`Library`
        :raise: SelfUnload if :attr:`suspend_on_error` is True and error occurred
        :raise: HTTPError if library is not found
        :raise: ImportError if library doesn't have any class which is a subclass of :obj:`loader.Library`
        :raise: ImportError if library name doesn't end with `Lib`
        :raise: RuntimeError if library throws in :method:`init`
        :raise: RuntimeError if library classname exists in :obj:`Modules`.libraries
        """

        from . import utils  # Avoiding circular import
        from .loader import USER_INSTALL, VALID_PIP_PACKAGES
        from .translations import Strings

        def _raise(e: Exception):
            if suspend_on_error:
                raise SelfSuspend("Required library is not available or is corrupted.")

            raise e

        if not utils.check_url(url):
            _raise(ValueError("Invalid url for library"))

        code = await utils.run_sync(requests.get, url)
        code.raise_for_status()
        code = code.text

        if re.search(r"# ?scope: ?hikka_min", code):
            ver = tuple(
                map(
                    int,
                    re.search(r"# ?scope: ?hikka_min ((\d+\.){2}\d+)", code)[1].split(
                        "."
                    ),
                )
            )

            if version.__version__ < ver:
                _raise(
                    RuntimeError(
                        f"Library requires Hikkaduwa version {'{}.{}.{}'.format(*ver)}+"
                    )
                )

        module = f"hikka.libraries.{url.replace('%', '%%').replace('.', '%d')}"
        origin = f"<library {url}>"

        spec = importlib.machinery.ModuleSpec(
            module,
            StringLoader(code, origin),
            origin=origin,
        )
        try:
            instance = importlib.util.module_from_spec(spec)
            sys.modules[module] = instance
            spec.loader.exec_module(instance)
        except ImportError as e:
            logger.info(
                "Library loading failed, attemping dependency installation (%s)",
                e.name,
            )
            # Let's try to reinstall dependencies
            try:
                requirements = list(
                    filter(
                        lambda x: not x.startswith(("-", "_", ".")),
                        map(
                            str.strip,
                            VALID_PIP_PACKAGES.search(code)[1].split(),
                        ),
                    )
                )
            except TypeError:
                logger.warning(
                    "No valid pip packages specified in code, attemping"
                    " installation from error"
                )
                requirements = [e.name]

            logger.debug("Installing requirements: %s", requirements)

            if not requirements or _did_requirements:
                _raise(e)

            pip = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "-q",
                "--disable-pip-version-check",
                "--no-warn-script-location",
                *["--user"] if USER_INSTALL else [],
                *requirements,
            )

            rc = await pip.wait()

            if rc != 0:
                _raise(e)

            importlib.invalidate_caches()

            kwargs = utils.get_kwargs()
            kwargs["_did_requirements"] = True

            return await self._mod_import_lib(**kwargs)  # Try again

        lib_obj = next(
            (
                value()
                for value in vars(instance).values()
                if inspect.isclass(value) and issubclass(value, Library)
            ),
            None,
        )

        if not lib_obj:
            _raise(ImportError("Invalid library. No class found"))

        if not lib_obj.__class__.__name__.endswith("Lib"):
            _raise(
                ImportError(
                    "Invalid library. Classname {} does not end with 'Lib'".format(
                        lib_obj.__class__.__name__
                    )
                )
            )

        lib_obj.source_url = url.strip("/")
        lib_obj.allmodules = self.allmodules
        lib_obj.internal_init()

        for old_lib in self.allmodules.libraries:
            if old_lib.name == lib_obj.name and (
                not isinstance(getattr(old_lib, "version", None), tuple)
                and not isinstance(getattr(lib_obj, "version", None), tuple)
                or old_lib.version >= lib_obj.version
            ):
                logger.debug("Using existing instance of library %s", old_lib.name)
                return old_lib

        if hasattr(lib_obj, "init"):
            if not callable(lib_obj.init):
                _raise(ValueError("Library init() must be callable"))

            try:
                await lib_obj.init()
            except Exception:
                _raise(RuntimeError("Library init() failed"))

        if hasattr(lib_obj, "config"):
            if not isinstance(lib_obj.config, LibraryConfig):
                _raise(
                    RuntimeError("Library config must be a `LibraryConfig` instance")
                )

            libcfg = lib_obj.db.get(
                lib_obj.__class__.__name__,
                "__config__",
                {},
            )

            for conf in lib_obj.config:
                with contextlib.suppress(Exception):
                    lib_obj.config.set_no_raise(
                        conf,
                        (
                            libcfg[conf]
                            if conf in libcfg
                            else os.environ.get(f"{lib_obj.__class__.__name__}.{conf}")
                            or lib_obj.config.getdef(conf)
                        ),
                    )

        if hasattr(lib_obj, "strings"):
            lib_obj.strings = Strings(lib_obj, self.translator)

        lib_obj.translator = self.translator

        for old_lib in self.allmodules.libraries:
            if old_lib.name == lib_obj.name:
                if hasattr(old_lib, "on_lib_update") and callable(
                    old_lib.on_lib_update
                ):
                    await old_lib.on_lib_update(lib_obj)

                replace_all_refs(old_lib, lib_obj)
                logger.debug(
                    "Replacing existing instance of library %s with updated object",
                    lib_obj.name,
                )
                return lib_obj

        self.allmodules.libraries += [lib_obj]
        return lib_obj


class Library:
    """All external libraries must have a class-inheritant from this class"""

    if typing.TYPE_CHECKING:
        allmodules: "Modules"

    def internal_init(self) -> None:
        self.name = self.__class__.__name__
        self.db = self.allmodules.db
        self._db = self.allmodules.db
        self.client = self.allmodules.client
        self._client = self.allmodules.client
        self.tg_id = self._client.tg_id
        self._tg_id = self._client.tg_id
        self.lookup = self.allmodules.lookup
        self.get_prefix = self.allmodules.get_prefix
        self.inline = self.allmodules.inline

    def _lib_get(
        self,
        key: str,
        default: JSONSerializable | None = None,
    ) -> JSONSerializable:
        return self._db.get(self.__class__.__name__, key, default)

    def _lib_set(self, key: str, value: JSONSerializable) -> bool:
        self._db.set(self.__class__.__name__, key, value)

    def _lib_pointer(
        self,
        key: str,
        default: JSONSerializable | None = None,
    ) -> JSONSerializable | PointerDict | PointerList:
        return self._db.pointer(self.__class__.__name__, key, default)


class LoadError(Exception):
    """Tells user, why your module can't be loaded, if raised in `client_ready`"""

    def __init__(self, error_message: str):  # skipcq: PYL-W0231
        self._error = error_message

    def __str__(self) -> str:
        return self._error


class CoreOverwriteError(LoadError):
    """Is being raised when core module or command is overwritten"""

    def __init__(
        self,
        module: str | None = None,
        command: str | None = None,
    ):
        self.type = "module" if module else "command"
        self.target = module or command
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f"{'Module' if self.type == 'module' else 'command'} {self.target} will not"
            " be overwritten, because it's core"
        )


class CoreUnloadError(Exception):
    """Is being raised when user tries to unload core module"""

    def __init__(self, module: str):
        self.module = module
        super().__init__()

    def __str__(self) -> str:
        return f"Module {self.module} will not be unloaded, because it's core"


class SelfUnload(Exception):
    """Silently unloads module, if raised in `client_ready`"""

    def __init__(self, error_message: str = ""):
        super().__init__()
        self._error = error_message

    def __str__(self) -> str:
        return self._error


class SelfSuspend(Exception):
    """
    Silently suspends module, if raised in `client_ready`
    Commands and watcher will not be registered if raised
    Module won't be unloaded from db and will be unfreezed after restart, unless
    the exception is raised again
    """

    def __init__(self, error_message: str = ""):
        super().__init__()
        self._error = error_message

    def __str__(self) -> str:
        return self._error


class StopLoop(Exception):
    """Stops the loop, in which is raised"""


class ModuleConfig(dict):
    """Stores config for modules and apparently libraries"""

    def __init__(self, *entries: "str | ConfigValue"):
        if all(isinstance(entry, ConfigValue) for entry in entries):
            # New config format processing
            self._config = {config.option: config for config in entries}
        else:
            # Legacy config processing
            keys = []
            values = []
            defaults = []
            docstrings = []
            for i, entry in enumerate(entries):
                if i % 3 == 0:
                    keys += [entry]
                elif i % 3 == 1:
                    values += [entry]
                    defaults += [entry]
                else:
                    docstrings += [entry]

            self._config = {
                key: ConfigValue(option=key, default=default, doc=doc)
                for key, default, doc in zip(keys, defaults, docstrings)
            }

        super().__init__(
            {option: config.value for option, config in self._config.items()}
        )

    def getdoc(self, key: str, message: Message | None = None) -> str:
        """Get the documentation by key"""
        ret = self._config[key].doc

        if callable(ret):
            try:
                # Compatibility tweak
                # does nothing in Hikka
                ret = ret(message)
            except Exception:
                ret = ret()

        return ret

    def getdef(self, key: str) -> str:
        """Get the default value by key"""
        return self._config[key].default

    def __setitem__(self, key: str, value: typing.Any):
        self._config[key].value = value
        super().__setitem__(key, value)

    def set_no_raise(self, key: str, value: typing.Any):
        self._config[key].set_no_raise(value)
        super().__setitem__(key, value)

    def __getitem__(self, key: str) -> typing.Any:
        try:
            return self._config[key].value
        except KeyError:
            return None

    def reload(self) -> None:
        for key in self._config:
            super().__setitem__(key, self._config[key].value)

    def change_validator(
        self,
        key: str,
        validator: typing.Callable[[JSONSerializable], JSONSerializable],
    ) -> None:
        self._config[key].validator = validator


LibraryConfig = ModuleConfig


class _Placeholder:
    """Placeholder to determine if the default value is going to be set"""


@dataclass(repr=True)
class ConfigValue:
    option: str
    default: typing.Any = None
    doc: typing.Callable[[], str] | str = "No description"
    value: typing.Any = field(default_factory=_Placeholder)
    validator: typing.Callable[[JSONSerializable], JSONSerializable] | None = None
    on_change: typing.Callable[[], typing.Awaitable] | typing.Callable | None = None

    def __post_init__(self):
        if isinstance(self.value, _Placeholder):
            self.value = self.default

    def set_no_raise(self, value: typing.Any) -> bool:
        """
        Sets the config value w/o ValidationError being raised
        Should not be used uninternally
        """
        return self.__setattr__("value", value, ignore_validation=True)

    def __setattr__(
        self,
        key: str,
        value: typing.Any,
        *,
        ignore_validation: bool = False,
    ):
        if key == "value":
            with contextlib.suppress(Exception):
                value = ast.literal_eval(value)

            # Convert value to list if it's tuple just not to mess up
            # with json conversions
            if isinstance(value, (set, tuple)):
                value = list(value)

            if isinstance(value, list):
                value = [
                    item.strip() if isinstance(item, str) else item for item in value
                ]

            if self.validator is not None:
                if value is not None:
                    from . import validators

                    try:
                        value = self.validator.validate(value)
                    except validators.ValidationError as e:
                        if not ignore_validation:
                            raise e

                        logger.debug(
                            "Config value was broken (%s), so it was reset to %s",
                            value,
                            self.default,
                        )

                        value = self.default
                else:
                    defaults = {
                        "String": "",
                        "Integer": 0,
                        "Boolean": False,
                        "Series": [],
                        "Float": 0.0,
                    }

                    if self.validator.internal_id in defaults:
                        logger.debug(
                            "Config value was None, so it was reset to %s",
                            defaults[self.validator.internal_id],
                        )
                        value = defaults[self.validator.internal_id]

            # This attribute will tell the `Loader` to save this value in db
            self._save_marker = True

        object.__setattr__(self, key, value)

        if key == "value" and not ignore_validation and callable(self.on_change):
            with contextlib.suppress(Exception):
                if inspect.iscoroutinefunction(self.on_change):
                    asyncio.ensure_future(self.on_change())
                else:
                    self.on_change()


def _get_members(
    mod: Module,
    ending: str,
    attribute: str | None = None,
    strict: bool = False,
) -> dict:
    """Get method of module, which end with ending"""
    return {
        (
            method_name.rsplit(ending, maxsplit=1)[0]
            if (method_name == ending if strict else method_name.endswith(ending))
            else method_name
        ).lower(): getattr(mod, method_name)
        for method_name in dir(mod)
        if not isinstance(getattr(type(mod), method_name, None), property)
        and callable(getattr(mod, method_name))
        and (
            (method_name == ending if strict else method_name.endswith(ending))
            or attribute
            and getattr(getattr(mod, method_name), attribute, False)
        )
    }


def get_commands(mod: Module) -> dict:
    """Introspect the module to get its commands"""
    return _get_members(mod, "cmd", "is_command")


def get_inline_handlers(mod: Module) -> dict:
    """Introspect the module to get its inline handlers"""
    return _get_members(mod, "_inline_handler", "is_inline_handler")


def get_callback_handlers(mod: Module) -> dict:
    """Introspect the module to get its callback handlers"""
    return _get_members(mod, "_callback_handler", "is_callback_handler")


def get_watchers(mod: Module) -> dict:
    """Introspect the module to get its watchers"""
    return _get_members(
        mod,
        "watcher",
        "is_watcher",
        strict=True,
    )

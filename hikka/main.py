"""Main script, where all the fun starts"""

#    Friendly Telegram (telegram userbot)
#    Copyright (C) 2018-2021 The Authors

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.


# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html


import argparse
import asyncio
import collections
import contextlib
import importlib
import json
import logging
import os
import random
import socket
import sqlite3
import typing
from getpass import getpass
from pathlib import Path

import hikkatl
from hikkatl import events
from hikkatl.errors import (
    ApiIdInvalidError,
    AuthKeyDuplicatedError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from hikkatl.network.connection import (
    ConnectionTcpFull,
    ConnectionTcpMTProxyRandomizedIntermediate,
)
from hikkatl.password import compute_check
from hikkatl.sessions import MemorySession, SQLiteSession
from hikkatl.tl.functions.account import GetPasswordRequest
from hikkatl.tl.functions.auth import CheckPasswordRequest

from . import database, loader, utils, version
from .dispatcher import CommandDispatcher
from .qr import QRCode
from .tl_cache import CustomTelegramClient
from .translations import Translator
from .version import __version__

web_available = False

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

BASE_PATH = Path(BASE_DIR)
CONFIG_PATH = BASE_PATH / "config.json"

IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "")
IS_WSL = False
with contextlib.suppress(Exception):
    from platform import uname

    if "microsoft-standard" in uname().release:
        IS_WSL = True
IS_WINDOWS = (os.name == "nt") and (not IS_WSL)

# fmt: off
LATIN_MOCK = [
    "Amor", "Arbor", "Astra", "Aurum", "Bellum", "Caelum",
    "Calor", "Candor", "Carpe", "Celer", "Certo", "Cibus",
    "Civis", "Clemens", "Coetus", "Cogito", "Conexus",
    "Consilium", "Cresco", "Cura", "Cursus", "Decus",
    "Deus", "Dies", "Digitus", "Discipulus", "Dominus",
    "Donum", "Dulcis", "Durus", "Elementum", "Emendo",
    "Ensis", "Equus", "Espero", "Fidelis", "Fides",
    "Finis", "Flamma", "Flos", "Fortis", "Frater", "Fuga",
    "Fulgeo", "Genius", "Gloria", "Gratia", "Gravis",
    "Habitus", "Honor", "Hora", "Ignis", "Imago",
    "Imperium", "Inceptum", "Infinitus", "Ingenium",
    "Initium", "Intra", "Iunctus", "Iustitia", "Labor",
    "Laurus", "Lectus", "Legio", "Liberi", "Libertas",
    "Lumen", "Lux", "Magister", "Magnus", "Manus",
    "Memoria", "Mens", "Mors", "Mundo", "Natura",
    "Nexus", "Nobilis", "Nomen", "Novus", "Nox",
    "Oculus", "Omnis", "Opus", "Orbis", "Ordo", "Os",
    "Pax", "Perpetuus", "Persona", "Petra", "Pietas",
    "Pons", "Populus", "Potentia", "Primus", "Proelium",
    "Pulcher", "Purus", "Quaero", "Quies", "Ratio",
    "Regnum", "Sanguis", "Sapientia", "Sensus", "Serenus",
    "Sermo", "Signum", "Sol", "Solus", "Sors", "Spes",
    "Spiritus", "Stella", "Summus", "Teneo", "Terra",
    "Tigris", "Trans", "Tribuo", "Tristis", "Ultimus",
    "Unitas", "Universus", "Uterque", "Valde", "Vates",
    "Veritas", "Verus", "Vester", "Via", "Victoria",
    "Vita", "Vox", "Vultus", "Zephyrus"
]
# fmt: on


def generate_app_name() -> str:
    """
    Generate random app name
    :return: Random app name
    :example: "Cresco Cibus Consilium"
    """
    return " ".join(random.choices(LATIN_MOCK, k=3))


def get_app_name() -> str:
    """
    Generates random app name or gets the saved one of present
    :return: App name
    :example: "Cresco Cibus Consilium"
    """
    if not (app_name := get_config_key("app_name")):
        app_name = generate_app_name()
        save_config_key("app_name", app_name)

    return app_name


# try:
#     import uvloop

#     uvloop.install()
# except Exception:
#     pass


def run_config():
    """Load configurator.py"""
    from . import configurator

    return configurator.api_config(IS_TERMUX or None)


def get_config_key(key: str) -> typing.Union[str, bool]:
    """
    Parse and return key from config
    :param key: Key name in config
    :return: Value of config key or `False`, if it doesn't exist
    """
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get(key, False)
    except FileNotFoundError:
        return False


def save_config_key(key: str, value: str) -> bool:
    """
    Save `key` with `value` to config
    :param key: Key name in config
    :param value: Desired value in config
    :return: `True` on success, otherwise `False`
    """
    try:
        # Try to open our newly created json config
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        # If it doesn't exist, just default config to none
        # It won't cause problems, bc after new save
        # we will create new one
        config = {}

    # Assign config value
    config[key] = value
    # And save config
    CONFIG_PATH.write_text(json.dumps(config, indent=4))
    return True


def gen_port(cfg: str = "port", no8080: bool = False) -> int:
    """
    Generates random free port in case of VDS.
    :returns: Integer value of generated port
    """

    # But for own server we generate new free port, and assign to it
    if port := get_config_key(cfg):
        return port

    # If we didn't get port from config, generate new one
    # First, try to randomly get port
    while port := random.randint(1024, 65536):
        if socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(
            ("localhost", port)
        ):
            break

    return port


def parse_arguments() -> dict:
    """
    Parses the arguments
    :returns: Dictionary with arguments
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port",
        dest="port",
        action="store",
        default=gen_port(),
        type=int,
    )
    parser.add_argument("--phone", "-p", action="append")
    parser.add_argument(
        "--qr-login",
        dest="qr_login",
        action="store_true",
        help=(
            "Use QR code login instead of phone number (will only work if scanned from"
            " another device)"
        ),
    )
    parser.add_argument(
        "--data-root",
        dest="data_root",
        default="",
        help="Root path to store session files in",
    )
    parser.add_argument(
        "--no-auth",
        dest="no_auth",
        action="store_true",
        help="Disable authentication and API token input, exitting if needed",
    )
    parser.add_argument(
        "--proxy-host",
        dest="proxy_host",
        action="store",
        help="MTProto proxy host, without port",
    )
    parser.add_argument(
        "--proxy-port",
        dest="proxy_port",
        action="store",
        type=int,
        help="MTProto proxy port",
    )
    parser.add_argument(
        "--proxy-secret",
        dest="proxy_secret",
        action="store",
        help="MTProto proxy secret",
    )
    parser.add_argument(
        "--root",
        dest="disable_root_check",
        action="store_true",
        help="Disable `force_insecure` warning",
    )
    parser.add_argument(
        "--proxy-pass",
        dest="proxy_pass",
        action="store_true",
        help="Open proxy pass tunnel on start (not needed on setup)",
    )
    parser.add_argument(
        "--no-tty",
        dest="tty",
        action="store_false",
        default=True,
        help="Do not print colorful output using ANSI escapes",
    )
    arguments = parser.parse_args()
    logging.debug(arguments)
    return arguments


class SuperList(list):
    """
    Makes able: await self.allclients.send_message("foo", "bar")
    """

    def __getattribute__(self, attr: str) -> typing.Any:
        if hasattr(list, attr):
            return list.__getattribute__(self, attr)

        for obj in self:
            attribute = getattr(obj, attr)
            if callable(attribute):
                if asyncio.iscoroutinefunction(attribute):

                    async def foobar(*args, **kwargs):
                        return [await getattr(_, attr)(*args, **kwargs) for _ in self]

                    return foobar
                return lambda *args, **kwargs: [
                    getattr(_, attr)(*args, **kwargs) for _ in self
                ]

            return [getattr(x, attr) for x in self]


class InteractiveAuthRequired(Exception):
    """Is being rased by Telethon, if phone is required"""


def raise_auth():
    """Raises `InteractiveAuthRequired`"""
    raise InteractiveAuthRequired()


class Hikka:
    """Main userbot instance, which can handle multiple clients"""

    def __init__(self):
        global BASE_DIR, BASE_PATH, CONFIG_PATH
        self.omit_log = False
        self.arguments = parse_arguments()
        if self.arguments.data_root:
            BASE_DIR = self.arguments.data_root
            BASE_PATH = Path(BASE_DIR)
            CONFIG_PATH = BASE_PATH / "config.json"
        self.loop = asyncio.get_event_loop()

        self.clients = SuperList()
        self.ready = asyncio.Event()
        self._read_sessions()
        self._get_api_token()
        self._get_proxy()

        self.web = None  # maybe some modules use this..?

    def _get_proxy(self):
        """
        Get proxy tuple from --proxy-host, --proxy-port and --proxy-secret
        and connection to use (depends on proxy - provided or not)
        """
        if (
            self.arguments.proxy_host is not None
            and self.arguments.proxy_port is not None
            and self.arguments.proxy_secret is not None
        ):
            logging.debug(
                "Using proxy: %s:%s",
                self.arguments.proxy_host,
                self.arguments.proxy_port,
            )
            self.proxy, self.conn = (
                (
                    self.arguments.proxy_host,
                    self.arguments.proxy_port,
                    self.arguments.proxy_secret,
                ),
                ConnectionTcpMTProxyRandomizedIntermediate,
            )
            return

        self.proxy, self.conn = None, ConnectionTcpFull

    def _read_sessions(self):
        """Gets sessions from environment and data directory"""
        self.sessions = []
        self.sessions += [
            SQLiteSession(
                os.path.join(
                    BASE_DIR,
                    session.rsplit(".session", maxsplit=1)[0],
                )
            )
            for session in filter(
                lambda f: f.startswith("hikka-") and f.endswith(".session"),
                os.listdir(BASE_DIR),
            )
        ]

    def _get_api_token(self):
        """Get API Token from disk or environment"""
        api_token_type = collections.namedtuple("api_token", ("ID", "HASH"))

        # Try to retrieve credintials from config, or from env vars
        try:
            # Legacy migration
            if not get_config_key("api_id"):
                api_id, api_hash = (
                    line.strip()
                    for line in (Path(BASE_DIR) / "api_token.txt")
                    .read_text(encoding="utf-8")
                    .splitlines()
                )
                save_config_key("api_id", int(api_id))
                save_config_key("api_hash", api_hash)
                (Path(BASE_DIR) / "api_token.txt").unlink()
                logging.debug("Migrated api_token.txt to config.json")

            api_token = api_token_type(
                get_config_key("api_id"),
                get_config_key("api_hash"),
            )
        except FileNotFoundError:
            try:
                from . import api_token
            except ImportError:
                try:
                    api_token = api_token_type(
                        os.environ["api_id"],
                        os.environ["api_hash"],
                    )
                except KeyError:
                    api_token = None

        self.api_token = api_token

    async def _get_token(self):
        """Reads or waits for user to enter API credentials"""
        while self.api_token is None:
            if self.arguments.no_auth:
                return

            run_config()
            importlib.invalidate_caches()
            self._get_api_token()

    async def save_client_session(self, client: CustomTelegramClient):
        if hasattr(client, "tg_id"):
            telegram_id = client.tg_id
        else:
            if not (me := await client.get_me()):
                raise RuntimeError("Attempted to save non-inited session")

            telegram_id = me.id
            client._tg_id = telegram_id
            client.tg_id = telegram_id
            client.hikka_me = me

        session = SQLiteSession(
            os.path.join(
                BASE_DIR,
                f"hikka-{telegram_id}",
            )
        )

        session.set_dc(
            client.session.dc_id,
            client.session.server_address,
            client.session.port,
        )

        session.auth_key = client.session.auth_key

        session.save()
        client.session = session
        # Set db attribute to this client in order to save
        # custom bot nickname from web
        # TODO: still needed?
        client.hikka_db = database.Database(client)
        await client.hikka_db.init()

    async def _phone_login(self, client: CustomTelegramClient) -> bool:
        phone = input(
            "Enter phone: "
            if IS_TERMUX or self.arguments.tty
            else "Enter phone: "
        )

        await client.start(phone)

        await self.save_client_session(client)
        self.clients += [client]
        return True

    async def _initial_setup(self) -> bool:
        """Responsible for first start"""
        if self.arguments.no_auth:
            return False

        client = CustomTelegramClient(
            MemorySession(),
            self.api_token.ID,
            self.api_token.HASH,
            connection=self.conn,
            proxy=self.proxy,
            connection_retries=None,
            device_model=get_app_name(),
            system_version="Windows 10",
            app_version=".".join(map(str, __version__)) + " x64",
            lang_code="en",
            system_lang_code="en-US",
        )
        await client.connect()

        print(
            "You can use QR-code to login from another device (your friend's"
            " phone, for example)."
        )

        if (
            input("Use QR code? [y/N]: ").lower() != "y"
        ):
            return await self._phone_login(client)

        print("Loading QR code...")
        qr_login = await client.qr_login()

        def print_qr():
            qr = QRCode()
            qr.add_data(qr_login.url)
            qr.print_ascii(tty=False)
            print("Scan the QR code above to log in.")
            print("Press Ctrl+C to cancel.")

        async def qr_login_poll() -> bool:
            logged_in = False
            while not logged_in:
                try:
                    logged_in = await qr_login.wait(10)
                except asyncio.TimeoutError:
                    try:
                        await qr_login.recreate()
                        print_qr()
                    except SessionPasswordNeededError:
                        return True
                except SessionPasswordNeededError:
                    return True
                except KeyboardInterrupt:
                    return None

            return False

        if (qr_logined := await qr_login_poll()) is None:
            return await self._phone_login(client)

        if qr_logined:
            password = await client(GetPasswordRequest())
            while True:
                _2fa = getpass(
                    f"Enter 2FA password ({password.hint}): "
                    if IS_TERMUX or self.arguments.tty
                    else f"Enter 2FA password ({password.hint}): "
                )
                try:
                    await client._on_login(
                        (
                            await client(
                                CheckPasswordRequest(
                                    compute_check(password, _2fa.strip())
                                )
                            )
                        ).user
                    )
                except PasswordHashInvalidError:
                    print("Invalid 2FA password!")
                except FloodWaitError as e:
                    seconds, minutes, hours = (
                        e.seconds % 3600 % 60,
                        e.seconds % 3600 // 60,
                        e.seconds // 3600,
                    )
                    seconds, minutes, hours = (
                        f"{seconds} second(-s)",
                        f"{minutes} minute(-s) " if minutes else "",
                        f"{hours} hour(-s) " if hours else "",
                    )
                    print(
                        "You got FloodWait error! Please wait"
                        f" {hours}{minutes}{seconds}"
                    )
                    return False
                else:
                    break

        print("Logged in successfully!")
        await self.save_client_session(client)
        self.clients += [client]
        return True

    async def _init_clients(self) -> bool:
        """
        Reads session from disk and inits them
        :returns: `True` if at least one client started successfully
        """
        for session in self.sessions.copy():
            try:
                client = CustomTelegramClient(
                    session,
                    self.api_token.ID,
                    self.api_token.HASH,
                    connection=self.conn,
                    proxy=self.proxy,
                    connection_retries=None,
                    device_model=get_app_name(),
                    system_version="Windows 10",
                    app_version=".".join(map(str, __version__)) + " x64",
                    lang_code="en",
                    system_lang_code="en-US",
                )

                await client.start(
                    phone=(
                        lambda: input(
                            "Enter phone: "
                            if IS_TERMUX or self.arguments.tty
                            else "Enter phone: "
                        )
                    )
                )
                client.phone = "never gonna give you up"

                self.clients += [client]
            except sqlite3.OperationalError:
                logging.error(
                    (
                        "Check that this is the only instance running. "
                        "If that doesn't help, delete the file '%s'"
                    ),
                    session.filename,
                )
                continue
            except (TypeError, AuthKeyDuplicatedError):
                Path(session.filename).unlink(missing_ok=True)
                self.sessions.remove(session)
            except (ValueError, ApiIdInvalidError):
                # Bad API hash/ID
                run_config()
                return False
            except PhoneNumberInvalidError:
                logging.error(
                    "Phone number is incorrect. Use international format (+XX...) "
                    "and don't put spaces in it."
                )
                self.sessions.remove(session)
            except InteractiveAuthRequired:
                logging.error(
                    "Session %s was terminated and re-auth is required",
                    session.filename,
                )
                self.sessions.remove(session)

        return bool(self.sessions)

    async def amain_wrapper(self, client: CustomTelegramClient):
        """Wrapper around amain"""
        async with client:
            first = True
            me = await client.get_me()
            client._tg_id = me.id
            client.tg_id = me.id
            client.hikka_me = me
            while await self.amain(first, client):
                first = False

    async def _badge(self, client: CustomTelegramClient):
        """Call the badge in shell"""
        try:
            # import git

            # repo = git.Repo()

            # build = utils.get_git_hash()
            # diff = repo.git.log([f"HEAD..origin/{version.branch}", "--oneline"])
            # upd = "Update required" if diff else "Up-to-date"

            logo = (
                "█ █ █ █▄▀ █▄▀ ▄▀█\n"
                "█▀█ █ █ █ █ █ █▀█\n\n"
                # f"• Build: {build[:7]}\n"
                f"• Version: {'.'.join(list(map(str, list(__version__))))}\n"
                # f"• {upd}\n"
            )

            if not self.omit_log:
                print(logo)
                # logging.debug(
                #     "\n🌘 Hikka %s #%s (%s) started\n%s",
                #     ".".join(list(map(str, list(__version__)))),
                #     build[:7],
                #     upd,
                #     web_url,
                # )
                logging.debug(
                    "\n🌘 Hikka %s started",
                    ".".join(list(map(str, list(__version__)))),
                )
                self.omit_log = True

            await client.hikka_inline.bot.send_animation(
                logging.getLogger().handlers[0].get_logid_by_client(client.tg_id),
                "https://github.com/hikariatama/assets/raw/master/hikka_banner.mp4",
                # caption=(
                #     "🌘 <b>Hikka {} started!</b>\n\n🌳 <b>GitHub commit SHA: <a"
                #     ' href="https://github.com/hikariatama/Hikka/commit/{}">{}</a></b>\n✊'
                #     " <b>Update status: {}</b>\n<b>{}</b>".format(
                #         ".".join(list(map(str, list(__version__)))),
                #         build,
                #         build[:7],
                #         upd,
                #         web_url,
                #     )
                # ),
                caption=(
                    "🌘 <b>Hikka {} started!</b>"
                    .format(
                        ".".join(list(map(str, list(__version__)))),
                    )
                ),
            )

            logging.debug(
                "· Started for %s · Prefix: «%s» ·",
                client.tg_id,
                client.hikka_db.get(__name__, "command_prefix", False) or ".",
            )
        except Exception:
            logging.exception("Badge error")

    async def _add_dispatcher(
        self,
        client: CustomTelegramClient,
        modules: loader.Modules,
        db: database.Database,
    ):
        """Inits and adds dispatcher instance to client"""
        dispatcher = CommandDispatcher(modules, client, db)
        client.dispatcher = dispatcher
        modules.check_security = dispatcher.check_security

        client.add_event_handler(
            dispatcher.handle_incoming,
            events.NewMessage,
        )

        client.add_event_handler(
            dispatcher.handle_incoming,
            events.ChatAction,
        )

        client.add_event_handler(
            dispatcher.handle_command,
            events.NewMessage(forwards=False),
        )

        client.add_event_handler(
            dispatcher.handle_command,
            events.MessageEdited(),
        )

        client.add_event_handler(
            dispatcher.handle_raw,
            events.Raw(),
        )

    async def amain(self, first: bool, client: CustomTelegramClient):
        """Entrypoint for async init, run once for each user"""
        client.parse_mode = "HTML"
        await client.start()

        db = database.Database(client)
        client.hikka_db = db
        await db.init()

        logging.debug("Got DB")
        logging.debug("Loading logging config...")

        translator = Translator(client, db)

        await translator.init()
        modules = loader.Modules(client, db, self.clients, translator)
        client.loader = modules

        await self._add_dispatcher(client, modules, db)

        await modules.register_all(None)
        modules.send_config()
        await modules.send_ready()

        if first:
            await self._badge(client)

        await client.run_until_disconnected()

    async def _main(self):
        """Main entrypoint"""
        save_config_key("port", self.arguments.port)
        await self._get_token()

        if (
            not self.clients and not self.sessions or not await self._init_clients()
        ) and not await self._initial_setup():
            return

        self.loop.set_exception_handler(
            lambda _, x: logging.error(
                "Exception on event loop! %s",
                x["message"],
                exc_info=x.get("exception", None),
            )
        )

        await asyncio.gather(*[self.amain_wrapper(client) for client in self.clients])

    def main(self):
        """Main entrypoint"""
        self.loop.run_until_complete(self._main())
        self.loop.close()


hikkatl.extensions.html.CUSTOM_EMOJIS = not get_config_key("disable_custom_emojis")

hikka = Hikka()

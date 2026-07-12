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
import importlib
import logging
import os
import random
import socket
import typing
from pathlib import Path

import orjson
import pyrogram
from pyrogram import idle

from . import database, loader
from .client import HikkaClient
from .dispatcher import CommandDispatcher
from .translations import Translator
from .version import __version__

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

BASE_PATH = Path(BASE_DIR)
CONFIG_PATH = BASE_PATH / "config.json"

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
    if not (app_name := typing.cast(str, get_config_key("app_name"))):
        app_name = generate_app_name()
        save_config_key("app_name", app_name)

    return app_name


def run_config() -> None:
    """Load configurator.py"""
    from . import configurator

    configurator.api_config()


def get_config_key(key: str) -> (str | int | float | dict | list) | typing.Literal[
    False
]:
    """
    Parse and return key from config
    :param key: Key name in config
    :return: Value of config key or `False`, if it doesn't exist
    """
    try:
        return orjson.loads(CONFIG_PATH.read_text(encoding="utf-8")).get(key, False)
    except FileNotFoundError:
        return False


def save_config_key(key: str, value: str | int | float | dict | list) -> bool:
    """
    Save `key` with `value` to config
    :param key: Key name in config
    :param value: Desired value in config
    :return: `True` on success, otherwise `False`
    """
    try:
        # Try to open our newly created json config
        config = orjson.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        # If it doesn't exist, just default config to none
        # It won't cause problems, bc after new save
        # we will create new one
        config = {}

    # Assign config value
    config[key] = value
    # And save config
    CONFIG_PATH.write_bytes(orjson.dumps(config))
    return True


def gen_port(cfg: str = "port", no8080: bool = False) -> int:
    """
    Generates random free port in case of VDS.
    :returns: Integer value of generated port
    """

    # But for own server we generate new free port, and assign to it
    if port := typing.cast(int, get_config_key(cfg)):
        return port

    # If we didn't get port from config, generate new one
    # First, try to randomly get port
    while port := random.randint(1024, 65536):
        if socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(
            ("localhost", port)
        ):
            break

    return port


def parse_arguments() -> argparse.Namespace:
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


class Hikka:
    """Main userbot instance"""

    instance: "Hikka"

    def __init__(self):
        Hikka.instance = self

        global BASE_DIR, BASE_PATH, CONFIG_PATH
        self.arguments: argparse.Namespace = parse_arguments()
        if self.arguments.data_root:
            BASE_DIR = self.arguments.data_root
            BASE_PATH = Path(BASE_DIR)
            CONFIG_PATH = BASE_PATH / "config.json"
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()

        # TODO
        self.proxy: tuple
        self.conn: typing.Any

        self.client: HikkaClient

        self.ready = asyncio.Event()
        self._get_api_token()
        self._get_proxy()

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
                None,  # ConnectionTcpMTProxyRandomizedIntermediate
            )
            return

        self.proxy, self.conn = None, None  # ConnectionTcpFull

    def _get_api_token(self):
        """Get API Token from disk or environment"""
        api_token_type = collections.namedtuple("api_token", ("ID", "HASH"))

        # Try to retrieve credentials from config, or from env vars
        try:
            api_token = api_token_type(
                get_config_key("api_id"),
                get_config_key("api_hash"),
            )
        except FileNotFoundError:
            try:
                from . import api_token  # type: ignore[reportAttributeAccessIssue]
            except ImportError:
                try:
                    api_token = api_token_type(
                        os.environ["api_id"],
                        os.environ["api_hash"],
                    )
                except KeyError:
                    api_token = None

        self.api_token: api_token_type | None = api_token

    async def _get_token(self):
        """Reads or waits for user to enter API credentials"""
        while self.api_token is None:
            if self.arguments.no_auth:
                return

            run_config()
            importlib.invalidate_caches()
            self._get_api_token()

    async def amain_wrapper(self):
        """Wrapper around amain"""
        async with self.client:
            self.client.me = await self.client.get_me()
            self.client.tg_id = self.client.hikka_me.id
            await self.amain()

    @staticmethod
    async def _badge(client: HikkaClient):
        """Call the badge in shell"""
        try:
            logo: str = (
                "█ █ █ █▄▀ █▄▀ ▄▀█\n"
                "█▀█ █ █ █ █ █ █▀█\n\n"
                f"• Version: {'.'.join(list(map(str, list(__version__))))}\n"
            )

            print(logo)
            logging.debug(
                "\n🌘 Hikkaduwa %s started",
                ".".join(list(map(str, list(__version__)))),
            )

            await client.hikka_inline.bot.send_message(
                logging.getLogger().handlers[0].get_logid_by_client(client.tg_id),  # type: ignore
                "🌘 <b>Hikkaduwa {} started!</b>".format(
                    ".".join(list(map(str, list(__version__)))),
                ),
            )

            logging.debug(
                "· Started for %s · Prefix: «%s» ·",
                client.tg_id,
                client.hikka_db.get(__name__, "command_prefix", False) or ".",
            )
        except Exception:
            logging.exception("Badge error")

    async def _add_dispatcher(self, /, modules: loader.Modules, db: database.Database):
        def cmd_filter(_, __, update: pyrogram.types.Update) -> bool:
            if not isinstance(update, pyrogram.types.Message):
                return False
            if update.forwards:
                return False
            if (not update.outgoing) and (update.chat.id != self.client.hikka_me.id):
                return False
            return True

        """Inits and adds dispatcher instance to client"""
        self.client.hikka_dispatcher = CommandDispatcher(modules, self.client, db)

        self.client.add_handler(
            handler=pyrogram.handlers.MessageHandler(
                callback=self.client.hikka_dispatcher.handle_incoming
            ),
            group=0,
        )

        # self.client.add_handler(
        #     pyrogram.handlers.DeletedMessagesHandler(
        #         self.client.hikka_dispatcher.handle_incoming
        #     )
        # )

        filter_cmd = pyrogram.filters.create(cmd_filter)

        self.client.add_handler(
            handler=pyrogram.handlers.MessageHandler(
                callback=self.client.hikka_dispatcher.handle_command,
                filters=filter_cmd,
            ),
            group=1,
        )

        self.client.add_handler(
            handler=pyrogram.handlers.EditedMessageHandler(
                callback=self.client.hikka_dispatcher.handle_command,
                filters=filter_cmd,
            ),
            group=1,
        )

        # self.client.add_handler(
        #     pyrogram.handlers.RawUpdateHandler(
        #         self.client.hikka_dispatcher.handle_raw,
        #     )
        # )

    async def amain(self):
        """Runs after the client connects, starts everything Hikka related"""
        db = database.Database(client=self.client)
        self.client.hikka_db = db
        await db.init()

        logging.debug("Got DB")
        logging.debug("Loading logging config...")

        translator = Translator(client=self.client, db=db)

        await translator.init()
        modules = loader.Modules(client=self.client, db=db, translator=translator)
        self.client._loader = modules
        self.client.hikka_inline = modules.inline

        await self._add_dispatcher(modules=modules, db=db)

        await modules.register_all(None)
        modules.send_config()
        await modules.send_ready()

        await self._badge(self.client)

        await idle()

    async def _main(self):
        """Async main entrypoint"""
        save_config_key("port", self.arguments.port)
        await self._get_token()

        self.client = HikkaClient(
            name="hikkaduwa",
            workdir=Path(__file__).parent.parent,
            api_id=self.api_token.ID,
            api_hash=self.api_token.HASH,
            device_model=get_app_name(),
            system_version="Windows 10",
            app_version=".".join(map(str, __version__)) + " x64",
            lang_code="en",
            system_lang_code="en-US",
            parse_mode=pyrogram.enums.ParseMode.HTML,
        )

        self.loop.set_exception_handler(
            lambda _, x: logging.error(
                "Exception on event loop! %s",
                x["message"],
                exc_info=x.get("exception", None),
            )
        )

        await self.amain_wrapper()

    def main(self):
        """Main entrypoint"""
        self.loop.run_until_complete(self._main())
        self.loop.close()


hikka = Hikka()

# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import atexit
import logging
import os
import random
import signal
import sys
import subprocess
from .platform import IS_WINDOWS


async def fw_protect():
    await asyncio.sleep(random.randint(1000, 3000) / 1000)


def get_startup_callback() -> callable:
    return lambda *_: os.execl(
        sys.executable,
        sys.executable,
        "-m",
        os.path.relpath(os.path.abspath(os.path.dirname(os.path.abspath(__file__)))),
        *sys.argv[1:],
    )


def restart_windows_test():
    # TODO
    subprocess.run(
        [
            sys.executable,
            "-m",
            os.path.relpath(
                os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
            ),
        ],
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


def die():
    """Platform-dependent way to kill the current process group"""
    if IS_WINDOWS:
        os.kill(os.getpid(), signal.SIGTERM)
        return

    os.killpg(os.getpgid(os.getpid()), signal.SIGTERM)


def restart():
    if "HIKKA_DO_NOT_RESTART" in os.environ:
        print(
            "Got in a loop, exiting\nYou probably need to manually remove existing"
            " packages and then restart Hikkaduwa. Run `pip uninstall -y telethon"
            " telethon-mod hikka-tl`, then restart Hikkaduwa."
        )
        sys.exit(0)

    logging.getLogger().setLevel(logging.CRITICAL)

    print("🔄 Restarting...")

    os.environ["HIKKA_DO_NOT_RESTART"] = "1"

    if IS_WINDOWS:
        restart_windows_test()
    else:
        signal.signal(signal.SIGTERM, get_startup_callback())

    die()

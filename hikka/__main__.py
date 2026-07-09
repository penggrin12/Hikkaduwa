"""Entry point. Checks for user and starts main script"""

# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import os
import sys


if sys.version_info < (3, 10, 0):
    print("🚫 Error: you must use at least Python version 3.10.0")
elif __package__ != "hikka":  # In case they did python __main__.py
    print("🚫 Error: you cannot run this as a script; you must execute as a package")
else:
    from . import log

    log.init()

    from . import main

    if "HIKKA_DO_NOT_RESTART" in os.environ:
        del os.environ["HIKKA_DO_NOT_RESTART"]

    try:
        main.hikka.main()  # Execute main function
    except KeyboardInterrupt:
        pass

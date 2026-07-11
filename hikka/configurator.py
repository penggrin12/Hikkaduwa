# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import string
import sys


def api_config() -> None:
    """Request API config from user and set"""
    from . import main

    print("Welcome to Hikkaduwa Userbot!")
    print("1. Go to https://my.telegram.org and login")
    print("2. Click on API development tools")
    print("3. Create a new application, by entering the required details")
    print("4. Copy your API ID and API hash")

    while api_id := input("Enter API ID: "):
        if api_id.isdigit():
            break

        print("Invalid ID")

    if not api_id:
        print("Cancelled")
        sys.exit(0)

    while api_hash := input("Enter API hash: "):
        if len(api_hash) == 32 and all(
            symbol in string.hexdigits for symbol in api_hash
        ):
            break

        print("Invalid hash")

    if not api_hash:
        print("Cancelled")
        sys.exit(0)

    main.save_config_key("api_id", int(api_id))
    main.save_config_key("api_hash", api_hash)
    print("API config saved")

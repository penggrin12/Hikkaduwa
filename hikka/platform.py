import contextlib
import os


IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "")
IS_WSL = False
with contextlib.suppress(Exception):
    from platform import uname

    if "microsoft-standard" in uname().release:
        IS_WSL = True
IS_WINDOWS = (os.name == "nt") and (not IS_WSL)

import contextlib
import os

IS_CODESPACES = "CODESPACES" in os.environ
IS_DOCKER = "DOCKER" in os.environ
IS_RAILWAY = "RAILWAY" in os.environ
IS_GOORM = "GOORM" in os.environ
IS_LAVHOST = "LAVHOST" in os.environ
IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "")
IS_WSL = False
with contextlib.suppress(Exception):
    from platform import uname

    if "microsoft-standard" in uname().release:
        IS_WSL = True
IS_WINDOWS = (os.name == "nt") and (not IS_WSL)

import os
import subprocess
import sys
from asyncio.subprocess import PIPE, create_subprocess_exec
from typing import Iterable

USER_INSTALL = ("PIP_TARGET" not in os.environ) and ("VIRTUAL_ENV" not in os.environ)


class PipException(Exception):
    def __init__(self, code: int, stdout: str, stderr: str) -> None:
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(self.stderr)


class Pip:
    @staticmethod
    def _get_args(packages: Iterable[str]) -> list[str]:
        if uv := os.environ.get("UV", None):
            # `uv add` modifies the pyproject
            return [uv, "pip", "install", *packages]

        return [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "--disable-pip-version-check",
            "--no-warn-script-location",
            *(["--user"] if USER_INSTALL else []),
            *packages,
        ]

    @staticmethod
    async def install(*packages: str | None) -> None:
        exec, *args = Pip._get_args(package for package in packages if package)
        process = await create_subprocess_exec(exec, *args, stdout=PIPE, stderr=PIPE)
        if rc := await process.wait():
            stdout: str = (
                (await process.stdout.read()).decode("utf-8") if process.stdout else ""
            )
            stderr: str = (
                (await process.stderr.read()).decode("utf-8") if process.stderr else ""
            )
            raise PipException(rc, stdout, stderr)

    @staticmethod
    def sync_install(*packages: str | None) -> None:
        process = subprocess.run(
            Pip._get_args(package for package in packages if package),
            capture_output=True,
        )

        if process.returncode:
            raise PipException(
                process.returncode,
                process.stdout.decode("utf-8"),
                process.stderr.decode("utf-8"),
            )

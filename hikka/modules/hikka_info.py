# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

from telethon.tl.types import Message
from telethon.utils import get_display_name

from .. import loader, utils, version


@loader.tds
class HikkaInfoMod(loader.Module):
    """Show userbot info"""

    strings = {"name": "HikkaInfo"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "custom_message",
                None,
                doc=lambda: self.strings("_cfg_cst_msg"),
            ),
            loader.ConfigValue(
                "custom_button",
                ["🥂 Fork's Github page", "https://github.com/penggrin12/Hikkaduwa"],
                lambda: self.strings("_cfg_cst_btn"),
                validator=loader.validators.Union(
                    loader.validators.Series(loader.validators.String(), fixed_len=2),
                    loader.validators.NoneType(),
                ),
            ),
            loader.ConfigValue(
                "banner_url",
                None,
                lambda: self.strings("_cfg_banner"),
                validator=loader.validators.Link(),
            ),
        )

    def _render_info(self, inline: bool) -> str:
        me = '<b><a href="tg://user?id={}">{}</a></b>'.format(
            self._client.hikka_me.id,
            utils.escape_html(get_display_name(self._client.hikka_me)),
        )
        commit = utils.get_commit_url()
        branch: str = utils.get_git_branch() or "Unknown"
        _version = f'<i>{".".join(list(map(str, list(version.__version__))))}</i>'
        prefix = f"«<code>{utils.escape_html(self.get_prefix())}</code>»"
        modules_count = len(self.allmodules.modules)
        platform = utils.get_named_platform()

        return (
            ("" if self.config["custom_message"] else "<b>🌘 Hikkaduwa</b>\n")
            + self.config["custom_message"].format(
                me=me,
                version=_version,
                build=commit,
                prefix=prefix,
                platform=platform,
                upd="",
                uptime=utils.formatted_uptime(),
                cpu_usage=utils.get_cpu_usage(),
                ram_usage=f"{utils.get_ram_usage()} MB",
                branch=branch,
            )
            if self.config["custom_message"]
            else (
                f'🌘 <b>Hikkaduwa</b>\n\n'
                f'😎 <b>{self.strings("owner")}:</b> {me}\n\n'
                f'☀️ <b>{self.strings("commit")}:</b> {commit} on <code>{branch}</code>\n'
                f'🌙 <b>{self.strings("version")}:</b> {_version}\n\n'
                f'⚙️ <b>{self.strings("modules")}:</b> {modules_count}\n'
                f'⌨️ <b>{self.strings("prefix")}:</b> {prefix}\n'
                f'⌛️ <b>{self.strings("uptime")}:</b> {utils.formatted_uptime()}\n\n'
                f'⚡️ <b>{self.strings("cpu_usage")}:</b> <i>~{utils.get_cpu_usage()} %</i>\n'
                f'💼 <b>{self.strings("ram_usage")}:</b> <i>~{utils.get_ram_usage()} MB</i>\n'
                f'<b>{platform}</b>'
            )
        )

    def _get_mark(self):
        return (
            {
                "text": self.config["custom_button"][0],
                "url": self.config["custom_button"][1],
            }
            if self.config["custom_button"]
            else None
        )

    @loader.command()
    async def infocmd(self, message: Message):
        await self.inline.form(
            message=message,
            text=self._render_info(True),
            reply_markup=self._get_mark(),
            **({"photo": self.config["banner_url"]} if self.config["banner_url"] else {}),
        )

    @loader.command()
    async def hikkainfo(self, message: Message):
        await utils.answer(message, self.strings("desc"))

    @loader.command()
    async def setinfo(self, message: Message):
        if not (args := utils.get_args_html(message)):
            return await utils.answer(message, self.strings("setinfo_no_args"))

        self.config["custom_message"] = args
        await utils.answer(message, self.strings("setinfo_success"))

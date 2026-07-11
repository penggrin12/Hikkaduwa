"""Utilities"""

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

import asyncio
import atexit as _atexit
import contextlib
import functools
import html
import inspect
import io
import json
import logging
import os
import random
import re
import shlex
import signal
import string
import time
import typing
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

import asyncstdlib

# import git
import grapheme
import pyrogram.errors
import pyrogram.utils
import requests
from aiogram.types import Message as AiogramMessage
from pyrogram.types import Chat, Message, MessageEntity, User

from . import hints
from ._internal import fw_protect
from .inline.types import InlineCall, InlineMessage
from .types import HikkaReplyMarkup, ListLike, MessageLike, Module

if typing.TYPE_CHECKING:
    from .client import HikkaClient

emoji_pattern = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f680-\U0001f6ff"  # transport & map symbols
    "\U0001f1e0-\U0001f1ff"  # flags (iOS)
    "]+",
    flags=re.UNICODE,
)

parser = pyrogram.client.Parser(None)
logger = logging.getLogger(__name__)

_T = typing.TypeVar("_T")


def get_entity_id(entity: hints.Entity) -> int:
    """
    Get entity ID
    :param entity: Entity to get ID from
    :return: Entity ID
    """
    if entity.id is None:
        raise ValueError("There is no entity id")
    return entity.id


async def entitylike_to_id(client: "HikkaClient", entity: hints.EntityLike) -> int:
    if isinstance(entity, int):
        return entity
    elif isinstance(entity, (pyrogram.types.User, pyrogram.types.Chat)):
        return get_entity_id(entity)
    elif isinstance(entity, str):
        if not (entity_id := (await client.get_chat(entity)).id):
            raise ValueError(f"Can't get entity id from string {entity}")
        return entity_id
    elif isinstance(
        entity,
        (
            pyrogram.raw.types.InputPeerUser,
            pyrogram.raw.types.PeerUser,
            pyrogram.raw.types.InputPeerUserFromMessage,
        ),
    ):
        return entity.user_id
    elif isinstance(
        entity,
        (
            pyrogram.raw.types.InputPeerChannel,
            pyrogram.raw.types.PeerChannel,
            pyrogram.raw.types.InputPeerChannelFromMessage,
        ),
    ):
        return entity.channel_id
    elif isinstance(
        entity, (pyrogram.raw.types.InputPeerChat, pyrogram.raw.types.PeerChat)
    ):
        return entity.chat_id
    elif isinstance(entity, pyrogram.raw.types.InputPeerSelf):
        return client.hikka_me.id

    raise ValueError(f"Can't get entity id from entity type {type(entity)}")


def get_args_raw(message: Message | str) -> str:
    """
    Get the parameters to the command as a raw string (not split)
    :param message: Message or string to get arguments from
    :return: Raw string of arguments
    """
    if isinstance(message, str):
        text = message
    else:
        if not (text := message.text):
            return ""

    return args[1] if len(args := text.split(maxsplit=1)) > 1 else ""


def get_args(message: Message | str) -> list[str]:
    """
    Get arguments from message
    :param message: Message or string to get arguments from
    :return: List of arguments
    """
    raw_args: str = get_args_raw(message)

    try:
        split = shlex.split(raw_args)
    except ValueError:
        return [raw_args]  # Cannot split, let's assume that it's just one long message

    return list(filter(lambda x: len(x) > 0, split))


def get_args_html(message: Message) -> str:
    """
    Get the parameters to the command as string with HTML (not split)
    :param message: Message to get arguments from
    :return: String with HTML arguments
    """

    raise NotImplementedError

    # raw_args: str = get_args_raw(message)
    # if not raw_args:
    #     return raw_args
    #
    # raw_text, entities = parser.parse(message)
    # raw_text = parser.add_surrogate(raw_text)
    #
    # try:
    #     command_len = raw_text.index(" ") + 1
    # except ValueError:
    #     return ""
    #
    # return parser.unparse(
    #     parser.del_surrogate(raw_text[command_len:]),
    #     relocate_entities(entities, -command_len, raw_text[command_len:]),
    # )


def get_args_split_by(
    message: Message | str,
    separator: str,
) -> list[str]:
    """
    Split args with a specific separator
    :param message: Message or string to get arguments from
    :param separator: Separator to split by
    :return: List of arguments
    """
    return [
        section.strip() for section in get_args_raw(message).split(separator) if section
    ]


def get_chat_id(message: Message | AiogramMessage) -> int:
    """
    Get the chat ID, but without -100 if it's a channel
    :param message: Message to get chat ID from
    :return: Chat ID
    """
    if (message.chat is None) or (message.chat.id is None):
        raise ValueError("There is no chat or chat id")
    if message.chat.id < 0:
        return pyrogram.utils.get_channel_id(message.chat.id)
    return message.chat.id


def escape_html(text: str, /) -> str:  # sourcery skip
    """
    Pass all untrusted/potentially corrupt input here
    :param text: Text to escape
    :return: Escaped text
    """
    return html.escape(str(text))


def escape_quotes(text: str, /) -> str:
    """
    Escape quotes to HTML quotes
    :param text: Text to escape
    :return: Escaped text
    """
    return escape_html(text).replace('"', "&quot;")


def get_base_dir() -> str:
    """
    Get directory of this file
    :return: Directory of this file
    """
    return get_dir(__file__)


def get_dir(mod: str) -> str:
    """
    Get directory of given module
    :param mod: Module's `__file__` to get directory of
    :return: Directory of given module
    """
    return os.path.abspath(os.path.dirname(os.path.abspath(mod)))


async def get_user(message: Message) -> User | None:
    """
    Get user who sent message, searching if not found easily
    :param message: Message to get user from
    :return: User who sent message
    """
    if message.from_user:
        return message.from_user

    logger.error(
        f"Cannot find the user that sent {message.chat.id if message.chat else '?'}/{message.id}"
    )
    return None


def run_sync(func: typing.Callable[..., _T], *args, **kwargs) -> asyncio.Future[_T]:
    """
    Run a non-async function in a new thread and return an awaitable
    :param func: Sync-only function to execute
    :return: Awaitable Future
    """
    return asyncio.get_event_loop().run_in_executor(
        executor=None, func=functools.partial(func, *args, **kwargs)
    )


def run_async(
    loop: asyncio.AbstractEventLoop, coro: typing.Coroutine[typing.Any, typing.Any, _T]
) -> _T:
    """
    Run an async function as a non-async function, blocking till it's done
    :param loop: Event loop to run the coroutine in
    :param coro: Coroutine to run
    :return: Result of the coroutine
    """
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


def censor(
    obj: _T,
    to_censor: typing.Iterable[str] | None = None,
    replace_with: str = "redacted_{count}_chars",
) -> _T:
    """
    May modify the original object, but don't rely on it
    :param obj: Object to censor, preferably telethon
    :param to_censor: Iterable of strings to censor
    :param replace_with: String to replace with, {count} will be replaced with the number of characters
    :return: Censored object
    """
    if to_censor is None:
        to_censor = ["phone"]

    for k, v in vars(obj).items():
        if k in to_censor:
            setattr(obj, k, replace_with.format(count=len(v)))
        elif k[0] != "_" and hasattr(v, "__dict__"):
            setattr(obj, k, censor(v, to_censor, replace_with))

    return obj


def relocate_entities(
    entities: list[MessageEntity], offset: int, text: str | None = None
) -> list[MessageEntity]:
    """
    Move all entities by offset (truncating at text)
    :param entities: List of entities
    :param offset: Offset to move by
    :param text: Text to truncate at
    :return: List of entities
    """
    length = len(text) if text is not None else 0

    for ent in entities.copy() if entities else ():
        ent.offset += offset
        if ent.offset < 0:
            ent.length += ent.offset
            ent.offset = 0
        if text is not None and ent.offset + ent.length > length:
            ent.length = length - ent.offset
        if ent.length <= 0:
            entities.remove(ent)

    return entities


def can_edit(message: Message) -> bool:
    return (
        (
            message.outgoing
            or (  # handles saved messages
                message.chat is not None
                and message.from_user is not None
                and (
                    message.chat.id
                    == message._client.hikka_me.id
                    == message.from_user.id
                )
            )
        )
        and (not message.via_bot)
        and (not message.forwards)
    )


async def answer_file(
    message: MessageLike,
    file: str | bytes | io.IOBase | pyrogram.types.InputMediaDocument,
    caption: str | None = None,
    **kwargs,
) -> MessageLike:
    """
    Use this to answer a message with a document
    :param message: Message to answer
    :param file: File to send - url, path or bytes
    :param caption: Caption to send
    :param kwargs: Extra kwargs to pass to `send_file`
    :return: Sent message

    :example:
        >>> await utils.answer_file(message, "test.txt")
        >>> await utils.answer_file(
            message,
            "https://mods.hikariatama.ru/badges/artai.jpg",
            "This is the cool module, check it out!",
        )
    """
    if isinstance(message, (InlineCall, InlineMessage)):
        message: Message | int = message.form["caller"]
        if isinstance(message, int):
            raise ValueError('form["caller"] must not be an int')

    if isinstance(file, pyrogram.types.InputMediaDocument):
        if file.media is None:
            raise ValueError("file.media must not be None")
        file = file.media
    elif isinstance(file, bytes):
        file = io.BytesIO(file)
    elif isinstance(file, io.IOBase):
        file = typing.cast(typing.BinaryIO, typing.cast(object, file))

    # noinspection PyProtectedMember
    client = message._client
    if (client is None) or (message.chat is None) or (message.chat.id is None):
        raise ValueError

    try:
        response = await client.send_document(
            message.chat.id,
            file,
            caption=caption or "",
            **kwargs,
        )
        if response is None:
            raise
    except Exception:
        if caption:
            logger.warning(
                "Failed to send file, sending plain text instead", exc_info=True
            )
            return await answer(message, caption, **kwargs)

        raise

    with contextlib.suppress(Exception):
        await message.delete()

    return response


async def answer(
    message: MessageLike | list[MessageLike],
    response: str | Message | bytes | io.BytesIO,
    *,
    reply_markup: HikkaReplyMarkup | None = None,
    **kwargs,
) -> MessageLike:
    """
    Use this to give the response to a command
    :param message: Message to answer to. Can be a tl message or hikka inline object
    :param response: Response to send
    :param reply_markup: Reply markup to send. If specified, inline form will be used
    :return: Message or inline object

    :example:
        >>> await utils.answer(message, "Hello world!")
        >>> await utils.answer(
            message,
            "https://some-url.com/photo.jpg",
            caption="Hello, this is your photo!",
            asfile=True,
        )
        >>> await utils.answer(
            message,
            "Hello world!",
            reply_markup={"text": "Hello!", "data": "world"},
            silent=True,
            disable_security=True,
        )
    """
    # Compatibility with FTG\GeekTG

    edit = False

    if isinstance(message, list):
        if not message:
            raise ValueError("Message (as a list) must not be empty")
        message = message[0]

    if reply_markup is not None:
        if not isinstance(reply_markup, (list, dict)):
            raise ValueError("reply_markup must be a list or dict")

        if reply_markup:
            kwargs.pop("message", None)
            if isinstance(message, (InlineMessage, InlineCall)):
                await message.edit(response, reply_markup, **kwargs)
                return message

            # noinspection PyProtectedMember
            client = typing.cast("HikkaClient | None", message._client)
            if (client is None) or (message.chat is None) or (message.chat.id is None):
                raise ValueError

            reply_markup = client.loader.inline.normalize_markup(reply_markup)
            result = await client.loader.inline.form(
                response,
                message=message if message.outgoing else get_chat_id(message),
                reply_markup=reply_markup,
                **kwargs,
            )
            return result

    if isinstance(message, (InlineMessage, InlineCall)):
        await message.edit(response)
        return message

    kwargs.setdefault(
        "link_preview_options", pyrogram.types.LinkPreviewOptions(is_disabled=True)
    )

    if not (edit := can_edit(message)):
        kwargs.setdefault(
            "reply_parameters",
            pyrogram.types.ReplyParameters(message_id=message.reply_to_message_id)
            if message.reply_to_message_id
            else None,
        )
    elif "reply_parameters" in kwargs:
        kwargs.pop("reply_parameters")

    if isinstance(response, str) and not kwargs.pop("asfile", False):
        parser_mode = (
            pyrogram.enums.ParseMode.HTML
            if kwargs.pop("parse_mode", "HTML") == "HTML"
            else pyrogram.enums.ParseMode.MARKDOWN
        )
        text, entities = (await parser.parse(response, parser_mode)).values()

        if len(text) >= 4096 and not hasattr(message, "hikka_grepped"):
            try:
                if not message._client.loader.inline.init_complete:
                    raise

                strings = list(smart_split(text, entities, 4096))

                if len(strings) > 10:
                    raise

                list_ = await message._client.loader.inline.list(
                    message=message,
                    strings=strings,
                )

                if not list_:
                    raise

                return list_
            except Exception:
                file = io.BytesIO(text.encode("utf-8"))
                file.name = "command_result.txt"

                reply_param = pyrogram.types.ReplyParameters(
                    message_id=kwargs.get("reply_to") or get_topic(message)
                )

                result = await message.answer_document(
                    file,
                    # FIXME: translations no more
                    caption=message._client.loader.lookup("translations").strings(
                        "too_long"
                    ),
                    reply_parameters=reply_param if reply_param.message_id else None,
                )
                if not result:
                    raise

                if message.outgoing:
                    await message.delete()

                return result

        return await (message.edit if edit else message.answer)(
            text=text,
            entities=(
                message_entities_from_raw(client=message._client, entities=entities)
                if entities
                else None or None
            ),
            **kwargs,
        )
    elif isinstance(response, Message):
        if message.media is None and (
            response.media is None
            or response.media == pyrogram.enums.MessageMediaType.WEB_PAGE
        ):
            return await message.edit(
                text=response.html_text,
                parse_mode=pyrogram.enums.ParseMode.HTML,
                link_preview_options=pyrogram.types.LinkPreviewOptions(
                    is_disabled=response.media
                    != pyrogram.enums.MessageMediaType.WEB_PAGE
                ),
            )
        else:
            return await message.answer(
                text=response.md_text,
                parse_mode=pyrogram.enums.ParseMode.HTML,
                **kwargs,
            )
    else:
        return await answer_file(message, response, **kwargs)

    typing.assert_never(message)


async def get_target(message: Message, arg_no: int = 0) -> int | None:
    """
    Get target from message
    :param message: Message to get target from
    :param arg_no: Argument number to get target from
    :return: Target's id if found
    """

    if any(
        entity.type == pyrogram.enums.MessageEntityType.TEXT_MENTION
        for entity in (message.entities or [])
    ):
        e = sorted(
            filter(
                lambda x: x.type == pyrogram.enums.MessageEntityType.TEXT_MENTION,
                message.entities,
            ),
            key=lambda x: x.offset,
        )[0]
        return e.user.id if e and e.user else None

    if len(get_args(message)) > arg_no:
        user = get_args(message)[arg_no]
    elif message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    elif message.from_user:
        return message.from_user.id
    else:
        return None

    try:
        entity = await message._client.get_chat(user)
    except ValueError:
        return None
    else:
        if isinstance(entity, (User, Chat)):
            return entity.id


def merge(a: dict, b: dict, /) -> dict:
    """
    Merge with replace dictionary `a` to dictionary `b`
    :param a: Dictionary to merge from
    :param b: Dictionary to merge to
    :return: Merged dictionary
    """
    # original implementation actually mutates b
    copy = b.copy()
    copy.update(a)
    return copy


async def set_avatar(
    client: "HikkaClient",
    peer: hints.Entity,
    avatar: str,
) -> bool:
    """
    Sets an entity avatar
    :param client: Client to use
    :param peer: Peer to set avatar to
    :param avatar: Desired avatar's URL
    :return: Avatar is set successfully
    """
    if peer.id is None:
        raise ValueError("peer's id cannot be None")

    if isinstance(avatar, str) and check_url(avatar):
        f = (
            await run_sync(
                requests.get,
                avatar,
            )
        ).content
    elif isinstance(avatar, bytes):
        f = avatar
    else:
        return False

    await fw_protect()
    if not (res := await client.set_chat_photo(chat_id=peer.id, photo=io.BytesIO(f))):
        return False

    await fw_protect()

    try:
        await res.delete()
    except pyrogram.errors.RPCError:
        pass

    return True


async def invite_inline_bot(
    client: "HikkaClient",
    peer: hints.EntityLike,
) -> None:
    """
    Invites inline bot to a chat
    :param client: Client to use
    :param peer: Peer to invite bot to
    :return: None
    :raise RuntimeError: If error occurred while inviting bot
    """

    peer_id: int = await entitylike_to_id(client, peer)

    try:
        await client.add_chat_members(
            chat_id=peer_id, user_ids=client.loader.inline.bot_id
        )
    except Exception as e:
        raise RuntimeError(
            "Can't invite inline bot to old asset chat, which is required by module"
        ) from e

    with contextlib.suppress(Exception):
        await client.promote_chat_member(
            chat_id=peer_id,
            user_id=client.loader.inline.bot_id,
            privileges=pyrogram.types.ChatPrivileges(can_restrict_members=True),
        )
        await client.set_administrator_title(
            chat_id=peer_id, user_id=client.loader.inline.bot_id, title="Hikkaduwa"
        )


async def asset_channel(
    client: "HikkaClient",
    title: str,
    description: str,
    *,
    channel: bool = False,
    silent: bool = False,
    archive: bool = False,
    invite_bot: bool = False,
    avatar: str | None = None,
    ttl: int | None = None,
    _folder: str | None = None,
) -> tuple[Chat, bool]:
    """
    Create new channel (if needed) and return its entity
    :param client: Telegram client to create channel by
    :param title: Channel title
    :param description: Description
    :param channel: Whether to create a channel or supergroup
    :param silent: Automatically mute channel
    :param archive: Automatically archive channel
    :param invite_bot: Add inline bot and assure it's in chat
    :param avatar: Url to an avatar to set as pfp of created peer
    :param ttl: Time to live for messages in channel
    :return: Peer and bool: is channel new or pre-existent
    """
    if (
        title in client.channels_cache
        and client.channels_cache[title]["exp"] > time.time()
    ):
        peer = client.channels_cache[title]["peer"]
        peer.id = pyrogram.utils.ZERO_CHANNEL_ID - peer.id
        return peer, False

    async for d in client.get_dialogs():
        if d.chat.title == title:
            client.channels_cache[title] = {"peer": d.chat, "exp": int(time.time())}
            if invite_bot:
                if await asyncstdlib.all(
                    participant.user.id != client.loader.inline.bot_id
                    async for participant in (d.chat.get_members(limit=100))
                    if participant.user
                ):
                    await fw_protect()
                    await invite_inline_bot(client, d.chat)

            d.chat.id = pyrogram.utils.ZERO_CHANNEL_ID - d.chat.id
            return d.chat, False

    await fw_protect()

    peer: Chat = await client.create_channel(title=title, description=description)
    peer_id: int | None = peer.id
    if not peer_id:
        raise ValueError(f"Can't create channel with title {title}")

    if invite_bot:
        await fw_protect()
        await invite_inline_bot(client, peer)

    if silent:
        await fw_protect()
        await dnd(client, peer, archive)
    elif archive:
        await fw_protect()
        await client.archive_chats(chat_ids=peer_id)

    if avatar:
        await fw_protect()
        await set_avatar(client, peer, avatar)

    if ttl:
        await fw_protect()
        await client.set_chat_ttl(chat_id=peer_id, ttl_seconds=ttl)

    client.channels_cache[title] = {"peer": peer, "exp": int(time.time())}
    peer.id = pyrogram.utils.ZERO_CHANNEL_ID - peer.id
    return peer, True


async def dnd(
    client: "HikkaClient", peer: hints.EntityLike, archive: bool = True
) -> bool:
    """
    Mutes and optionally archives peer
    :param peer: Anything entity-link
    :param archive: Archive peer, or just mute?
    :return: `True` on success, otherwise `False`
    """
    peer_id = await entitylike_to_id(client, peer)

    try:
        await client.update_chat_notifications(
            chat_id=peer_id, mute=True, show_previews=False
        )

        if archive:
            await fw_protect()
            await client.archive_chats(peer_id)
    except Exception as e:
        logger.exception("utils.dnd error", exc_info=e)
        return False

    return True


def get_link(user: User | Chat, /) -> str:
    """
    Get telegram permalink to entity
    :param user: User or channel
    :return: Link to entity
    """
    return (
        f"tg://user?id={user.id}"
        if isinstance(user, User)
        else (
            f"tg://resolve?domain={user.username}"
            if getattr(user, "username", None)
            else ""
        )
    )


def chunks(_list: ListLike, n: int, /) -> list[ListLike]:
    """
    Split provided `_list` into chunks of `n`
    :param _list: List to split
    :param n: Chunk size
    :return: List of chunks
    """
    return [_list[i : i + n] for i in range(0, len(_list), n)]


def get_named_platform() -> str:
    """
    Returns formatted platform name
    :return: Platform name
    """
    # from . import main
    #
    # if main.IS_WSL:
    #     return "🍀 WSL"
    #
    # if main.IS_TERMUX:
    #     return "🕶 Termux"
    #
    # if main.IS_WINDOWS:
    #     return "💻 Windows"

    return "📻 VDS"


def get_platform_emoji() -> str:
    """
    Returns custom emoji for current platform
    :return: Emoji entity in string
    """
    return "🌘🌘🌘"


def uptime() -> int:
    """
    Returns userbot uptime in seconds
    :return: Uptime in seconds
    """
    return round(time.perf_counter() - init_ts)


def formatted_uptime() -> str:
    """
    Returns formated uptime
    :return: Formatted uptime
    """
    return str(timedelta(seconds=uptime()))


def ascii_face() -> str:
    """
    Returns a cute ASCII-art face
    :return: ASCII-art face
    """
    return escape_html(
        random.choice(
            [
                "ヽ(๑◠ܫ◠๑)ﾉ",
                "(◕ᴥ◕ʋ)",
                "ᕙ(`▽´)ᕗ",
                "(✿◠‿◠)",
                "(▰˘◡˘▰)",
                "(˵ ͡° ͜ʖ ͡°˵)",
                "ʕっ•ᴥ•ʔっ",
                "( ͡° ᴥ ͡°)",
                "(๑•́ ヮ •̀๑)",
                "٩(^‿^)۶",
                "(っˆڡˆς)",
                "ψ(｀∇´)ψ",
                "⊙ω⊙",
                "٩(^ᴗ^)۶",
                "(´・ω・)っ由",
                "( ͡~ ͜ʖ ͡°)",
                "✧♡(◕‿◕✿)",
                "โ๏௰๏ใ ื",
                "∩｡• ᵕ •｡∩ ♡",
                "(♡´౪`♡)",
                "(◍＞◡＜◍)⋈。✧♡",
                "╰(✿´⌣`✿)╯♡",
                "ʕ•ᴥ•ʔ",
                "ᶘ ◕ᴥ◕ᶅ",
                "▼・ᴥ・▼",
                "ฅ^•ﻌ•^ฅ",
                "(΄◞ิ౪◟ิ‵)",
                "٩(^ᴗ^)۶",
                "ᕴｰᴥｰᕵ",
                "ʕ￫ᴥ￩ʔ",
                "ʕᵕᴥᵕʔ",
                "ʕᵒᴥᵒʔ",
                "ᵔᴥᵔ",
                "(✿╹◡╹)",
                "(๑￫ܫ￩)",
                "ʕ·ᴥ·　ʔ",
                "(ﾉ≧ڡ≦)",
                "(≖ᴗ≖✿)",
                "（〜^∇^ )〜",
                "( ﾉ･ｪ･ )ﾉ",
                "~( ˘▾˘~)",
                "(〜^∇^)〜",
                "ヽ(^ᴗ^ヽ)",
                "(´･ω･`)",
                "₍ᐢ•ﻌ•ᐢ₎*･ﾟ｡",
                "(。・・)_且",
                "(=｀ω´=)",
                "(*•‿•*)",
                "(*ﾟ∀ﾟ*)",
                "(☉⋆‿⋆☉)",
                "ɷ◡ɷ",
                "ʘ‿ʘ",
                "(。-ω-)ﾉ",
                "( ･ω･)ﾉ",
                "(=ﾟωﾟ)ﾉ",
                "(・ε・`*) …",
                "ʕっ•ᴥ•ʔっ",
                "(*˘︶˘*)",
            ]
        )
    )


def array_sum(array: list[list[_T]], /) -> list[_T]:
    """
    Performs basic sum operation on array
    :param array: Array to sum
    :return: Sum of array
    """
    result = []
    for item in array:
        result += item

    return result


def rand(size: int, /) -> str:
    """
    Return random string of len `size`
    :param size: Length of string
    :return: Random string
    """
    return "".join(
        [random.choice(string.ascii_lowercase + string.digits) for _ in range(size)]
    )


def smart_split(
    text: str,
    entities: list[MessageEntity],
    length: int = 4096,
    split_on: ListLike = ("\n", " "),
    min_length: int = 1,
) -> typing.Iterator[str]:
    """
    Split the message into smaller messages.
    A grapheme will never be broken. Entities will be displaced to match the right location. No inputs will be mutated.
    The end of each message except the last one is stripped of characters from [split_on]
    :param text: the plain text input
    :param entities: the entities
    :param length: the maximum length of a single message
    :param split_on: characters (or strings) which are preferred for a message break
    :param min_length: ignore any matches on [split_on] strings before this number of characters into each message
    :return: iterator, which returns strings

    :example:
        >>> utils.smart_split(
            *client.parser.parse(
                "<b>Hello, world!</b>"
            )
        )
        <<< ["<b>Hello, world!</b>"]
    """

    # Authored by @bsolute
    # https://t.me/LonamiWebs/27777

    encoded = text.encode("utf-16le")
    pending_entities = entities
    text_offset = 0
    bytes_offset = 0
    text_length = len(text)
    bytes_length = len(encoded)

    while text_offset < text_length:
        if bytes_offset + length * 2 >= bytes_length:
            yield parser.unparse(
                text[text_offset:],
                list(sorted(pending_entities, key=lambda x: x.offset)),
                is_html=True,
            )
            break

        codepoint_count = len(
            encoded[bytes_offset : bytes_offset + length * 2].decode(
                "utf-16le",
                errors="ignore",
            )
        )

        for search in split_on:
            search_index = text.rfind(
                search,
                text_offset + min_length,
                text_offset + codepoint_count,
            )
            if search_index != -1:
                break
        else:
            search_index = text_offset + codepoint_count

        split_index = grapheme.safe_split_index(text, search_index)

        split_offset_utf16 = (
            len(text[text_offset:split_index].encode("utf-16le"))
        ) // 2
        exclude = 0

        while (
            split_index + exclude < text_length
            and text[split_index + exclude] in split_on
        ):
            exclude += 1

        current_entities = []
        entities = pending_entities.copy()
        pending_entities = []

        for entity in entities:
            if (
                entity.offset < split_offset_utf16
                and entity.offset + entity.length > split_offset_utf16 + exclude
            ):
                # spans boundary
                current_entities.append(
                    _copy_tl(
                        entity,
                        length=split_offset_utf16 - entity.offset,
                    )
                )
                pending_entities.append(
                    _copy_tl(
                        entity,
                        offset=0,
                        length=entity.offset
                        + entity.length
                        - split_offset_utf16
                        - exclude,
                    )
                )
            elif entity.offset < split_offset_utf16 < entity.offset + entity.length:
                # overlaps boundary
                current_entities.append(
                    _copy_tl(
                        entity,
                        length=split_offset_utf16 - entity.offset,
                    )
                )
            elif entity.offset < split_offset_utf16:
                # wholly left
                current_entities.append(entity)
            elif (
                entity.offset + entity.length
                > split_offset_utf16 + exclude
                > entity.offset
            ):
                # overlaps right boundary
                pending_entities.append(
                    _copy_tl(
                        entity,
                        offset=0,
                        length=entity.offset
                        + entity.length
                        - split_offset_utf16
                        - exclude,
                    )
                )
            elif entity.offset + entity.length > split_offset_utf16 + exclude:
                # wholly right
                pending_entities.append(
                    _copy_tl(
                        entity,
                        offset=entity.offset - split_offset_utf16 - exclude,
                    )
                )

        current_text = text[text_offset:split_index]
        yield parser.unparse(
            current_text,
            list(sorted(current_entities, key=lambda x: x.offset)),
            is_html=True,
        )

        text_offset = split_index + exclude
        bytes_offset += len(current_text.encode("utf-16le"))


def _copy_tl(o: pyrogram.types.Object, **kwargs):
    d = o.__dict__
    del d["_"]
    d.update(kwargs)
    return o.__class__(**d)


def check_url(url: str) -> bool:
    """
    Statically checks url for validity
    :param url: URL to check
    :return: True if valid, False otherwise
    """
    try:
        return bool(urlparse(url).netloc)
    except Exception:
        return False


def get_git_branch() -> str | None:
    """
    (Hikkaduwa)

    Get current Hikkaduwa git branch
    :return: Head branch
    """

    # TODO: ultra hacky
    try:
        with open(Path(".") / Path(".git") / Path("HEAD"), "r") as file:
            return file.read().strip().replace("ref: refs/heads/", "")
    except Exception:
        return None


def get_git_hash() -> str | typing.Literal[False]:
    """
    Get current Hikkaduwa git hash
    :return: Git commit hash
    """

    # TODO: ultra hacky
    try:
        with open(
            Path(".")
            / Path(".git")
            / Path("refs")
            / Path("heads")
            / Path(get_git_branch() or "master"),
            "r",
        ) as file:
            return file.read().strip()
    except Exception:
        return False


def get_commit_url() -> str:
    """
    Get current Hikkaduwa git commit url
    :return: Git commit url
    """

    commit_hash = get_git_hash()
    return (
        f'<a href="https://github.com/penggrin12/Hikkaduwa/commit/{commit_hash}">{commit_hash[:7]}</a>'
        if commit_hash
        else "Unknown"
    )


def is_serializable(x: typing.Any, /) -> bool:
    """
    Checks if object is JSON-serializable
    :param x: Object to check
    :return: True if object is JSON-serializable, False otherwise
    """
    try:
        json.dumps(x)
        return True
    except Exception:
        return False


def get_lang_flag(countrycode: str) -> str:
    """
    Gets an emoji of specified countrycode
    :param countrycode: 2-letter countrycode
    :return: Emoji flag
    """
    if (
        len(
            code := [
                c
                for c in countrycode.lower()
                if c in string.ascii_letters + string.digits
            ]
        )
        == 2
    ):
        return "".join([chr(ord(c.upper()) + (ord("🇦") - ord("A"))) for c in code])

    return countrycode


def get_entity_url(entity: User, openmessage: bool = False) -> str:
    """
    Get link to object, if available
    :param entity: Entity to get url of
    :param openmessage: Use tg://openmessage link for users
    :return: Link to object or empty string
    """
    return (
        (
            f"tg://openmessage?id={entity.id}"
            if openmessage
            else f"tg://user?id={entity.id}"
        )
        if isinstance(entity, User)
        else (
            f"tg://resolve?domain={entity.username}"
            if getattr(entity, "username", None)
            else ""
        )
    )


async def get_message_link(message: Message, chat: Chat | None = None) -> str:
    """
    Get link to message
    :param message: Message to get link of
    :param chat: Chat, where message was sent
    :return: Link to message
    """
    if message.chat and (not message.chat.is_public):
        return (
            f"tg://openmessage?user_id={get_chat_id(message)}&message_id={message.id}"
        )

    if not chat and not (chat := message.chat):
        raise

    topic: int | None = get_topic(message)
    topic_affix = f"/{topic}" if topic else ""

    return (
        f"https://t.me/{chat.username}/{message.id}{topic_affix}"
        if chat.username
        else f"https://t.me/c/{chat.id}/{message.id}{topic_affix}"
    )


def remove_html(text: str, escape: bool = False, keep_emojis: bool = False) -> str:
    """
    Removes HTML tags from text
    :param text: Text to remove HTML from
    :param escape: Escape HTML
    :param keep_emojis: Keep custom emojis
    :return: Text without HTML
    """
    return (escape_html if escape else str)(
        re.sub(
            (
                r"(<\/?a.*?>|<\/?b>|<\/?i>|<\/?u>|<\/?strong>|<\/?em>|<\/?code>|<\/?strike>|<\/?del>|<\/?pre.*?>)"
                if keep_emojis
                else r"(<\/?a.*?>|<\/?b>|<\/?i>|<\/?u>|<\/?strong>|<\/?em>|<\/?code>|<\/?strike>|<\/?del>|<\/?pre.*?>|<\/?emoji.*?>)"
            ),
            "",
            text,
        )
    )


def get_kwargs() -> dict[str, typing.Any]:
    """
    Get kwargs of function, in which is called
    :return: kwargs
    """
    # https://stackoverflow.com/a/65927265/19170642
    keys, _, _, values = inspect.getargvalues(inspect.currentframe().f_back)
    return {key: values[key] for key in keys if key != "self"}


def mime_type(message: Message) -> str:
    """
    Get mime type of document in message
    :param message: Message with document
    :return: Mime type or empty string if not present
    """
    return (
        ""
        if not isinstance(message, Message) or not getattr(message, "media", False)
        else getattr(getattr(message, "media", False), "mime_type", False) or ""
    )


def find_caller(
    stack: list[inspect.FrameInfo] | None = None,
) -> typing.Any:
    """
    Attempts to find command in stack
    :param stack: Stack to search in
    :return: Command-caller or None
    """
    caller = next(
        (
            frame_info
            for frame_info in stack or inspect.stack()
            if hasattr(frame_info, "function")
            and any(
                inspect.isclass(cls_)
                and issubclass(cls_, Module)
                and cls_ is not Module
                for cls_ in frame_info.frame.f_globals.values()
            )
        ),
        None,
    )

    if not caller:
        return next(
            (
                frame_info.frame.f_locals["func"]
                for frame_info in stack or inspect.stack()
                if hasattr(frame_info, "function")
                and frame_info.function == "future_dispatcher"
                and (
                    "CommandDispatcher"
                    in getattr(getattr(frame_info, "frame", None), "f_globals", {})
                )
            ),
            None,
        )

    return next(
        (
            getattr(cls_, caller.function, None)
            for cls_ in caller.frame.f_globals.values()
            if inspect.isclass(cls_) and issubclass(cls_, Module)
        ),
        None,
    )


def message_entities_from_raw(
    client: "HikkaClient",
    entities: list[pyrogram.raw.base.MessageEntity],
) -> list[pyrogram.types.MessageEntity]:
    # TODO: users shouldn't be empty
    return list(
        map(lambda x: pyrogram.types.MessageEntity._parse(client, x, {}), entities)
    )


def validate_html(html: str) -> str:
    """
    Removes broken tags from HTML
    :param html: HTML to validate
    :return: Valid HTML
    """

    text, entities = run_async(
        asyncio.get_running_loop(), parser.parse(html, pyrogram.enums.ParseMode.HTML)
    ).values()
    return parser.unparse(escape_html(text), entities, True)


def iter_attrs(
    obj: typing.Any, /
) -> typing.Generator[tuple[str, typing.Any], typing.Any, None]:
    """
    Returns list of attributes of object
    :param obj: Object to iterate over
    :return: List of attributes and their values
    """
    return ((attr, getattr(obj, attr)) for attr in dir(obj))


def atexit(
    func: typing.Callable,
    use_signal: int | None = None,
    *args,
    **kwargs,
) -> None:
    """
    Calls function on exit
    :param func: Function to call
    :param use_signal: If passed, `signal` will be used instead of `atexit`
    :param args: Arguments to pass to function
    :param kwargs: Keyword arguments to pass to function
    :return: None
    """
    if use_signal:
        signal.signal(use_signal, lambda *_: func(*args, **kwargs))
        return

    _atexit.register(functools.partial(func, *args, **kwargs))


def get_topic(message: Message) -> int | None:
    """
    Get topic id of message
    :param message: Message to get topic of
    :return: int or None if not present
    """

    return message.topic.id if message.topic else None


def get_ram_usage() -> float:
    """Returns current process tree memory usage in MB"""
    try:
        import psutil

        current_process = psutil.Process(os.getpid())
        mem = current_process.memory_info()[0] / 2.0**20
        for child in current_process.children(recursive=True):
            mem += child.memory_info()[0] / 2.0**20

        return round(mem, 1)
    except Exception:
        return 0


def get_cpu_usage() -> float:
    """Returns current process tree CPU usage in %"""
    try:
        import psutil

        current_process = psutil.Process(os.getpid())
        cpu = current_process.cpu_percent()
        for child in current_process.children(recursive=True):
            cpu += child.cpu_percent()

        return round(cpu, 1)
    except Exception:
        return 0


init_ts = time.perf_counter()


# GeekTG Compatibility
def get_git_info() -> tuple[str, str]:
    """
    Get git info
    :return: Git info
    """
    hash_ = get_git_hash()
    return (
        hash_,
        f"https://github.com/penggrin12/Hikkaduwa/commit/{hash_}" if hash_ else "",
    )


def get_version_raw() -> str:
    """
    Get the version of the userbot
    :return: Version in format %s.%s.%s
    """
    from . import version

    return ".".join(map(str, list(version.__version__)))


get_platform_name = get_named_platform


def get_display_name(entity: hints.Entity) -> str:
    """
    Gets the display name for the given `User` or `Chat`.
    Returns an empty string otherwise.
    """
    if isinstance(entity, pyrogram.types.Chat) and entity.title:
        return entity.title
    elif entity.last_name and entity.first_name:
        return f"{entity.first_name} {entity.last_name}"
    elif entity.first_name:
        return entity.first_name
    elif entity.last_name:
        return entity.last_name
    return ""

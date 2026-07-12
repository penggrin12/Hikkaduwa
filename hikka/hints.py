import typing

from pyrogram import types
from pyrogram.raw.base import InputPeer, Peer

Phone: typing.TypeAlias = str
Username: typing.TypeAlias = str
PeerID: typing.TypeAlias = int
Entity: typing.TypeAlias = types.User | types.Chat

EntityLike: typing.TypeAlias = Phone | Username | PeerID | InputPeer | Peer | Entity
EntitiesLike: typing.TypeAlias = EntityLike | typing.Sequence[EntityLike]

MessageLike: typing.TypeAlias = str | types.Message  # dupe in types
MessageIDLike: typing.TypeAlias = int | types.Message

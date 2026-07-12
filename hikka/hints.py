import typing

from pyrogram import types
from pyrogram.raw.base import InputPeer, Peer

Phone = str
Username = str
PeerID = int
Entity = types.User | types.Chat

EntityLike = Phone | Username | PeerID | InputPeer | Peer | Entity
EntitiesLike = EntityLike | typing.Sequence[EntityLike]

MessageLike = str | types.Message  # dupe in types
MessageIDLike = int | types.Message

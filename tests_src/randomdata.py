import random
import string
from datetime import datetime, timezone, timedelta
from enum import Enum, IntEnum
from functools import partial
from typing import TypeVar, Type, Callable, Sequence, Optional

from wing_diagram.data._bungie_api.bungie_enums import MembershipType, CharacterType, GameMode, ClanMemberType
from wing_diagram.data.types.activities import Activity, ActivityWithPost
from wing_diagram.data.types.clan import Clan
from wing_diagram.data.types.individuals import Player, Membership, MinimalPlayer, Character, GroupMinimalPlayer, \
    MinimalPlayerWithClan
from wing_diagram.util.itertools import flatten
from wing_diagram.util.time import now, TimePeriod

_T = TypeVar("_T")


def random_string(length: int = 8) -> str:
    return "".join(random.sample(string.ascii_letters, length))


def random_int(max=100000000) -> int:
    return random.randint(0, max)


def random_datetime() -> datetime:
    return datetime.fromtimestamp(now().timestamp() - random_int(1_000_000), timezone.utc)


_T_Enum = TypeVar("_T_Enum", bound=Enum)


def random_enum(enum: Type[_T_Enum]) -> _T_Enum:
    return random.choice(list(enum))


def random_excluding(random_provider: Callable[[], _T], excluding: Sequence[_T]) -> _T:
    attempts = 1
    value = random_provider()
    while value in excluding and attempts < 1000:
        value = random_provider()
    if value in excluding:
        raise RuntimeError("random_excluding: unable to find satisfactory random value")
    return value

from typing import TypeVar, Callable, Sequence, Generic, Iterable

from pydantic import BaseModel

_T = TypeVar('_T')
_U = TypeVar('_U')
_K = TypeVar('_K')

class Differences(BaseModel, Generic[_T, _U]):
    in_both: Sequence[_T]
    in_first: Sequence[_T]
    in_second: Sequence[_U]

def find_differences(group1: Iterable[_T], key1: Callable[[_T], _K], group2: Iterable[_U], key2: Callable[[_U], _K]) -> Differences[_T, _U]:
    mapping1 = {key1(v): v for v in group1}
    mapping2 = {key2(v): v for v in group2}

    return Differences(
    in_both=[mapping1[k] for k in set(mapping1).intersection(set(mapping2))],
        in_first=[mapping1[k] for k in set(mapping1).difference(set(mapping2))],
        in_second=[mapping2[k] for k in set(mapping2).difference(set(mapping1))]
    )
from typing import Iterable, TypeVar, Optional, Sequence, Tuple, Callable

import itertools

_T = TypeVar("_T")
_K = TypeVar("_K")
_V = TypeVar("_V")


def first(iterable: Iterable[_T]) -> _T:
    try:
        return next(iter(iterable))
    except StopIteration:
        raise ValueError("first: none found")

def maybe_first(iterable: Iterable[_T]) -> Optional[_T]:
    try:
        return next(iter(iterable))
    except StopIteration:
        return None

def rest(iterable: Iterable[_T]) -> Iterable[_T]:
    try:
        it = iter(iterable)
        _ = next(it)
        return it
    except StopIteration:
        raise ValueError("no elements in iterable")

def flatten(iterable: Sequence[Sequence[_T]]) -> Sequence[_T]:
    return list(itertools.chain(*iterable))

def only(iterable: Iterable[_T]) -> _T:
    it = iter(iterable)
    try:
        val = next(it)
    except StopIteration:
        raise ValueError("only: none found")

    try:
        _ = next(it)
        raise ValueError("only: More than one element")
    except StopIteration:
        return val

def is_empty(iterable: Iterable[_T]) -> bool:
    try:
        it = iter(iterable)
        _ =next(it)
        return False
    except StopIteration:
        return True

def not_empty(iterable: Iterable[_T]) -> bool:
    return not is_empty(iterable)

def key_sort() -> Callable[[Tuple[_K, _V]],_K]:
    return lambda i: i[0]

def value_sort() -> Callable[[Tuple[_K, _V]],_V]:
    return lambda i: i[1]

def key_filter(predicate: Callable[[_K], bool]) -> Callable[[Tuple[_K, _V]],_K]:
    return lambda i: predicate(i[0])

def value_filter(predicate: Callable[[_K], bool]) -> Callable[[Tuple[_K, _V]],_K]:
    return lambda i: predicate(i[1])

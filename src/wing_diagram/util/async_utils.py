import asyncio
from typing import List, Coroutine, TypeVar, Any, Callable, Awaitable, Optional, Sequence, Mapping

T = TypeVar('T')


async def collect_results(coroutines: List[Coroutine[Any, Any, T]]) -> List[T]:
    tasks = []
    async with asyncio.TaskGroup() as tg:
        for coroutine in coroutines:
            tasks.append(tg.create_task(coroutine))

    results = []
    for task in tasks:
        results.append(task.result())

    return results

async def collect_map(coroutine_map: Mapping[str, Coroutine[Any, Any, T]]) -> Mapping[str, T]:
    tasks = []
    async with asyncio.TaskGroup() as tg:
        for coroutine in coroutine_map.values():
            tasks.append(tg.create_task(coroutine))

    results = {}
    for key, task in zip(coroutine_map.keys(), tasks):
        results[key] = task.result()

    return results

async def collect_map_with_exceptions(coroutine_map: Mapping[str, Coroutine[Any, Any, T]]
                                      ) -> Mapping[str, T | Exception]:
    tasks = []
    async with asyncio.TaskGroup() as tg:
        for coroutine in coroutine_map.values():
            tasks.append(tg.create_task(coroutine))

    results = {}
    for key, task in zip(coroutine_map.keys(), tasks):
        results[key] = task.result()

    return results


async def retrieve_paged(get_page: Callable[[int], Awaitable[Sequence[T]]],
                         enough: Optional[Callable[[Sequence[T]], bool]]
                         ) -> Sequence[T]:
    result = list(await get_page(0))

    if enough is None or len(result) == 0:
        return result

    n_pages = 1
    while not enough(result):
        additional_results = await get_page(n_pages)
        if len(additional_results) == 0:
            # Empty page returned, no more objects to search for.
            break
        result.extend(additional_results)
        n_pages += 1

    return result

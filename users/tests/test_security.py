import asyncio

import pytest

from app.core.security import get_password_hash, is_valid_password


async def _count_ticks_during(work) -> int:
    """How many times the event loop got to run something else during `work`.

    The whole claim about offloading bcrypt is that the loop stays free while a
    password is hashed. A blocking implementation yields the loop exactly once
    -- at the first await -- and the ticker never resumes until the hash is
    done, so this returns 1. An offloaded one lets it spin for the duration.
    """
    ticks = 0

    async def tick() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0)

    ticker = asyncio.create_task(tick())
    await asyncio.sleep(0)
    try:
        await work
    finally:
        ticker.cancel()
    return ticks


@pytest.mark.asyncio
async def test_hashing_a_password_leaves_the_event_loop_free() -> None:
    ticks = await _count_ticks_during(get_password_hash("a-password"))

    assert ticks > 100, f"loop only ran {ticks} times; bcrypt blocked it"


@pytest.mark.asyncio
async def test_verifying_a_password_leaves_the_event_loop_free() -> None:
    hashed = await get_password_hash("a-password")

    ticks = await _count_ticks_during(is_valid_password("a-password", hashed))

    assert ticks > 100, f"loop only ran {ticks} times; bcrypt blocked it"

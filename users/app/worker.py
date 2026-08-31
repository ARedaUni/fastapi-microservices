import asyncio

import uvloop

from app.core.redis import redis_config

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def test_task(ctx, word: str):
    await asyncio.sleep(10)
    return f"test task return {word}"


async def startup(ctx):
    print("start")


async def shutdown(ctx):
    print("end")


class WorkerSettings:
    functions = [test_task]
    redis_settings = redis_config.arq()
    on_startup = startup
    on_shutdown = shutdown
    handle_signals = False

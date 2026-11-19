"""Run a coroutine on an event loop that psycopg's async mode supports.

psycopg cannot use Windows' default ProactorEventLoop in async mode; the selector loop works on
every platform. Entry points that use the async Postgres checkpointer go through ``run``.
"""

import asyncio
import sys
from collections.abc import Coroutine
from typing import Any


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    if sys.platform == "win32":
        return asyncio.run(coro, loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(coro)

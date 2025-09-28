import asyncpg, os
from config.settings import DATABASE_URL
_POOL = None

async def init_pool():
    global _POOL
    if _POOL is None:
        url = DATABASE_URL
        if not url:
            raise RuntimeError("DATABASE_URL not set")
        _POOL = await asyncpg.create_pool(dsn=url, min_size=1, max_size=5, command_timeout=5)
    return _POOL

def pool():
    if _POOL is None:
        raise RuntimeError("DB pool not initialized. Call init_pool() in on_ready().")
    return _POOL

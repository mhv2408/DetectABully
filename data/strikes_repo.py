import time
from .db import pool

def _now(): return int(time.time())

async def strike_bump(guild_id: str, user_id: str, window_sec: int) -> tuple[int, int]:
    now = _now()
    async with pool().acquire() as con:
        row = await con.fetchrow("SELECT count, reset_at FROM strikes WHERE guild_id=$1 AND user_id=$2", guild_id, user_id)
        if (not row) or (now > row["reset_at"]):
            count, reset_at = 1, now + window_sec
        else:
            count, reset_at = row["count"] + 1, row["reset_at"]
        await con.execute("""
          INSERT INTO strikes (guild_id,user_id,count,reset_at,updated_at)
          VALUES ($1,$2,$3,$4,$5)
          ON CONFLICT (guild_id,user_id) DO UPDATE
            SET count=EXCLUDED.count, reset_at=EXCLUDED.reset_at, updated_at=EXCLUDED.updated_at
        """, guild_id, user_id, count, reset_at, now)
    return count, reset_at

async def strike_get(guild_id: str, user_id: str):
    async with pool().acquire() as con:
        return await con.fetchrow("SELECT count, reset_at FROM strikes WHERE guild_id=$1 AND user_id=$2", guild_id, user_id)

async def strike_clear(guild_id: str, user_id: str):
    async with pool().acquire() as con:
        await con.execute("DELETE FROM strikes WHERE guild_id=$1 AND user_id=$2", guild_id, user_id)

async def cleanup_expired_strikes(guild_id: str) -> int:
    """
    Remove all strike rows for this guild whose window has expired (reset_at < now).
    Returns the count of deleted rows.
    """
    now = _now()
    async with pool().acquire() as con:
        row = await con.fetchrow(
            """
            WITH del AS (
              DELETE FROM strikes
              WHERE guild_id = $1
                AND reset_at < $2
              RETURNING 1
            )
            SELECT COUNT(*)::int AS c FROM del
            """,
            guild_id, now
        )
        return int(row["c"])
import time
from .db import pool

def _now(): return int(time.time())

async def wl_add(guild_id: str, user_id: str, reason: str | None, added_by: str | None, expires_at: int | None = None):
    """
    Upsert whitelist entry and tell the caller whether we inserted or updated.
    Returns: {"inserted": bool, "updated": bool}
    """
    async with pool().acquire() as con:
        row = await con.fetchrow(
            """
            INSERT INTO whitelist (guild_id, user_id, reason, added_by, created_at, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (guild_id, user_id)
            DO UPDATE SET
              reason = EXCLUDED.reason,
              added_by = EXCLUDED.added_by,
              expires_at = EXCLUDED.expires_at
            RETURNING (xmax = 0) AS inserted;  -- Postgres trick: true if newly inserted
            """,
            guild_id, user_id, reason, added_by, _now(), expires_at
        )
        inserted = bool(row["inserted"])
        return {"inserted": inserted, "updated": (not inserted)}

async def wl_remove(guild_id: str, user_id: str):
    """
    Delete and report whether anything was removed.
    Returns: {"removed": bool}
    """
    async with pool().acquire() as con:
        row = await con.fetchrow(
            "DELETE FROM whitelist WHERE guild_id=$1 AND user_id=$2 RETURNING 1 AS removed",
            guild_id, user_id
        )
        return {"removed": bool(row)}

async def wl_is_whitelisted(guild_id: str, user_id: str) -> bool:
    async with pool().acquire() as con:
        row = await con.fetchrow(
            """
            SELECT 1
            FROM whitelist
            WHERE guild_id=$1 AND user_id=$2
              AND (expires_at IS NULL OR expires_at >= $3)
            """,
            guild_id, user_id, _now()
        )
        return bool(row)

async def wl_count(guild_id: str) -> int:
    async with pool().acquire() as con:
        row = await con.fetchrow("SELECT COUNT(*)::int AS c FROM whitelist WHERE guild_id=$1", guild_id)
        return int(row["c"])

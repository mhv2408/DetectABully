import time
from .db import pool

def _now(): return int(time.time())

# Immunity system constants
IMMUNITY_THRESHOLDS = {
    "trusted": 100,    # Immune to warnings (0.4-0.6)
    "veteran": 500,    # Immune to minor flags (0.6-0.7)  
    "guardian": 1000   # Only severe violations (0.8+)
}

POINT_VALUES = {
    "clean_message": 1,      # Per message with toxicity < 0.1
    "helpful_reaction": 3,   # Per helpful reaction given
    "quality_message": 5,    # Long message (>50 chars) with 0.0 toxicity
    "weekly_bonus": 50,      # 7 days without violations
    "strike_penalty": -10    # Per strike received
}

async def strike_bump(guild_id: str, user_id: str, window_sec: int, severity: str = "warn") -> tuple[int, int]:
    """Enhanced strike bump that also handles immunity penalties"""
    now = _now()
    async with pool().acquire() as con:
        row = await con.fetchrow(
            "SELECT count, reset_at, positive_points, immunity_level FROM strikes WHERE guild_id=$1 AND user_id=$2", 
            guild_id, user_id
        )
        
        if (not row) or (now > row["reset_at"]):
            count, reset_at = 1, now + window_sec
            # Preserve positive points but reset immunity if severe violation
            positive_points = row["positive_points"] if row else 0
            if severity == "severe":
                positive_points = max(0, positive_points - 100)  # Severe penalty
        else:
            count, reset_at = row["count"] + 1, row["reset_at"]
            positive_points = row["positive_points"] if row else 0
            
        # Apply strike penalty to positive points
        positive_points = max(0, positive_points + POINT_VALUES["strike_penalty"])
        
        # Recalculate immunity level
        immunity_level = _calculate_immunity_level(positive_points, count)
        
        await con.execute("""
          INSERT INTO strikes (guild_id,user_id,count,reset_at,updated_at,positive_points,immunity_level)
          VALUES ($1,$2,$3,$4,$5,$6,$7)
          ON CONFLICT (guild_id,user_id) DO UPDATE
            SET count=EXCLUDED.count, reset_at=EXCLUDED.reset_at, updated_at=EXCLUDED.updated_at,
                positive_points=EXCLUDED.positive_points, immunity_level=EXCLUDED.immunity_level
        """, guild_id, user_id, count, reset_at, now, positive_points, immunity_level)
    
    return count, reset_at

async def add_positive_points(guild_id: str, user_id: str, points: int, reason: str = "good_behavior"):
    """Add positive points for good behavior"""
    now = _now()
    async with pool().acquire() as con:
        # Get current data
        row = await con.fetchrow(
            "SELECT count, positive_points, last_positive_update FROM strikes WHERE guild_id=$1 AND user_id=$2",
            guild_id, user_id
        )
        
        if row:
            current_points = row["positive_points"] + points
            current_count = row["count"]
        else:
            current_points = points
            current_count = 0
            
        # Calculate new immunity level
        immunity_level = _calculate_immunity_level(current_points, current_count)
        
        await con.execute("""
          INSERT INTO strikes (guild_id,user_id,count,reset_at,updated_at,positive_points,immunity_level,last_positive_update)
          VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
          ON CONFLICT (guild_id,user_id) DO UPDATE
            SET positive_points=EXCLUDED.positive_points, immunity_level=EXCLUDED.immunity_level,
                last_positive_update=EXCLUDED.last_positive_update, updated_at=EXCLUDED.updated_at
        """, guild_id, user_id, current_count, now + 3600, now, current_points, immunity_level, now)

async def get_user_immunity(guild_id: str, user_id: str) -> dict:
    """Get user's current immunity status and points"""
    async with pool().acquire() as con:
        row = await con.fetchrow(
            "SELECT count, positive_points, immunity_level, last_positive_update FROM strikes WHERE guild_id=$1 AND user_id=$2",
            guild_id, user_id
        )
        
        if not row:
            return {
                "immunity_level": "none",
                "positive_points": 0,
                "strikes": 0,
                "next_threshold": IMMUNITY_THRESHOLDS["trusted"],
                "can_bypass_warnings": False,
                "can_bypass_minor_flags": False,
                "can_bypass_all_but_severe": False
            }
        
        immunity_level = row["immunity_level"] or "none"
        points = row["positive_points"] or 0
        
        # Calculate next threshold
        next_threshold = None
        if points < IMMUNITY_THRESHOLDS["trusted"]:
            next_threshold = IMMUNITY_THRESHOLDS["trusted"]
        elif points < IMMUNITY_THRESHOLDS["veteran"]:
            next_threshold = IMMUNITY_THRESHOLDS["veteran"]  
        elif points < IMMUNITY_THRESHOLDS["guardian"]:
            next_threshold = IMMUNITY_THRESHOLDS["guardian"]
        
        return {
            "immunity_level": immunity_level,
            "positive_points": points,
            "strikes": row["count"] or 0,
            "next_threshold": next_threshold,
            "can_bypass_warnings": immunity_level in ["trusted", "veteran", "guardian"],
            "can_bypass_minor_flags": immunity_level in ["veteran", "guardian"],
            "can_bypass_all_but_severe": immunity_level == "guardian"
        }

async def process_clean_message(guild_id: str, user_id: str, message_text: str, toxicity_score: float):
    """Process a clean message for positive points"""
    points = 0
    
    # Base clean message points
    if toxicity_score < 0.1:
        points += POINT_VALUES["clean_message"]
    
    # Quality message bonus
    if len(message_text) > 50 and toxicity_score == 0.0:
        points += POINT_VALUES["quality_message"]
    
    if points > 0:
        await add_positive_points(guild_id, user_id, points, "clean_message")

async def process_weekly_bonus(guild_id: str) -> list:
    """Award weekly bonuses to users with no violations in 7 days"""
    now = _now()
    week_ago = now - (7 * 24 * 3600)
    
    async with pool().acquire() as con:
        # Find users who haven't had strikes in the last 7 days
        rows = await con.fetch("""
            SELECT guild_id, user_id, positive_points
            FROM strikes 
            WHERE guild_id = $1 
              AND (updated_at < $2 OR count = 0)
              AND (last_positive_update < $3 OR last_positive_update IS NULL)
        """, guild_id, week_ago, now - (6 * 24 * 3600))  # Don't give bonus too frequently
        
        awarded_users = []
        for row in rows:
            new_points = row["positive_points"] + POINT_VALUES["weekly_bonus"]
            immunity_level = _calculate_immunity_level(new_points, 0)
            
            await con.execute("""
                UPDATE strikes 
                SET positive_points = $1, immunity_level = $2, last_positive_update = $3
                WHERE guild_id = $4 AND user_id = $5
            """, new_points, immunity_level, now, row["guild_id"], row["user_id"])
            
            awarded_users.append({
                "user_id": row["user_id"],
                "points_awarded": POINT_VALUES["weekly_bonus"],
                "total_points": new_points,
                "new_immunity": immunity_level
            })
        
        return awarded_users

async def get_immunity_leaderboard(guild_id: str, limit: int = 10) -> list:
    """Get top users by positive points"""
    async with pool().acquire() as con:
        rows = await con.fetch("""
            SELECT user_id, positive_points, immunity_level, count
            FROM strikes 
            WHERE guild_id = $1 AND positive_points > 0
            ORDER BY positive_points DESC
            LIMIT $2
        """, guild_id, limit)
        
        return [dict(row) for row in rows]

def _calculate_immunity_level(positive_points: int, strike_count: int) -> str:
    """Calculate immunity level based on points and behavior"""
    # Disqualify if too many recent strikes
    if strike_count >= 3:
        return "none"
    
    if positive_points >= IMMUNITY_THRESHOLDS["guardian"]:
        return "guardian"
    elif positive_points >= IMMUNITY_THRESHOLDS["veteran"]:
        return "veteran"
    elif positive_points >= IMMUNITY_THRESHOLDS["trusted"]:
        return "trusted"
    else:
        return "none"

# Existing functions remain the same
async def strike_get(guild_id: str, user_id: str):
    async with pool().acquire() as con:
        return await con.fetchrow(
            "SELECT count, reset_at, positive_points, immunity_level FROM strikes WHERE guild_id=$1 AND user_id=$2", 
            guild_id, user_id
        )

async def strike_clear(guild_id: str, user_id: str):
    async with pool().acquire() as con:
        await con.execute("DELETE FROM strikes WHERE guild_id=$1 AND user_id=$2", guild_id, user_id)

async def cleanup_expired_strikes(guild_id: str) -> int:
    """Remove expired strikes but preserve positive points for active users"""
    now = _now()
    async with pool().acquire() as con:
        # Only delete rows with no positive points and expired strikes
        row = await con.fetchrow("""
            WITH del AS (
              DELETE FROM strikes
              WHERE guild_id = $1
                AND reset_at < $2
                AND (positive_points IS NULL OR positive_points <= 0)
              RETURNING 1
            )
            SELECT COUNT(*)::int AS c FROM del
        """, guild_id, now)
        
        # Reset strike counts for expired but keep positive users
        await con.execute("""
            UPDATE strikes 
            SET count = 0, reset_at = $1
            WHERE guild_id = $2 AND reset_at < $1 AND positive_points > 0
        """, now, guild_id)
        
        return int(row["c"])
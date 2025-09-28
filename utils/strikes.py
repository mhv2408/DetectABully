"""
Strike system management for tracking user violations
"""

import time
from typing import Dict, List, Tuple, Optional
from config.settings import STRIKE_WINDOW_MINUTES

class StrikeManager:
    """Manages user strikes and violation history"""
    
    def __init__(self):
        # (guild_id, user_id) -> strike_data
        self.strikes: Dict[Tuple[int, int], dict] = {}
    
    def add_strike(self, guild_id: int, user_id: int, reason: str, 
                   severity: str, window_minutes: int = None) -> dict:
        """
        Add a strike for a user
        
        Returns:
            dict: Updated strike data for the user
        """
        if window_minutes is None:
            window_minutes = STRIKE_WINDOW_MINUTES
            
        key = (guild_id, user_id)
        now = time.time()
        
        # Get existing strikes or create new record
        strike_data = self.strikes.get(key, {
            "count": 0,
            "reset_at": now + window_minutes * 60,
            "history": [],
            "first_violation": now,
            "last_violation": now
        })
        
        # Reset strikes if window has expired
        if now > strike_data["reset_at"]:
            strike_data = {
                "count": 0,
                "reset_at": now + window_minutes * 60,
                "history": [],
                "first_violation": now,
                "last_violation": now
            }
        
        # Add new strike
        strike_data["count"] += 1
        strike_data["last_violation"] = now
        strike_data["history"].append({
            "reason": reason,
            "severity": severity,
            "timestamp": now
        })
        
        # Keep only last 20 strikes in history
        if len(strike_data["history"]) > 20:
            strike_data["history"] = strike_data["history"][-20:]
        
        self.strikes[key] = strike_data
        return strike_data
    
    def get_strikes(self, guild_id: int, user_id: int) -> dict:
        """Get current strike data for a user"""
        key = (guild_id, user_id)
        return self.strikes.get(key, {
            "count": 0,
            "reset_at": 0,
            "history": [],
            "first_violation": None,
            "last_violation": None
        })
    
    def clear_strikes(self, guild_id: int, user_id: int) -> bool:
        """
        Clear all strikes for a user
        
        Returns:
            bool: True if strikes were cleared, False if user had no strikes
        """
        key = (guild_id, user_id)
        if key in self.strikes:
            del self.strikes[key]
            return True
        return False
    
    def get_recent_violations(self, guild_id: int, user_id: int, 
                            hours: int = 24) -> List[dict]:
        """Get violations within the specified time window"""
        key = (guild_id, user_id)
        strike_data = self.strikes.get(key, {})
        history = strike_data.get("history", [])
        
        cutoff_time = time.time() - (hours * 3600)
        return [
            violation for violation in history 
            if violation["timestamp"] > cutoff_time
        ]
    
    def is_repeat_offender(self, guild_id: int, user_id: int, 
                          days: int = 7) -> bool:
        """Check if user is a repeat offender within timeframe"""
        recent = self.get_recent_violations(guild_id, user_id, hours=days*24)
        return len(recent) >= 3
    
    def get_violation_pattern(self, guild_id: int, user_id: int) -> dict:
        """Analyze user's violation patterns"""
        strike_data = self.get_strikes(guild_id, user_id)
        history = strike_data.get("history", [])
        
        if not history:
            return {"total": 0, "pattern": "clean"}
        
        # Count by severity
        severity_counts = {}
        for violation in history:
            severity = violation.get("severity", "unknown")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        # Determine pattern
        total = len(history)
        severe_count = severity_counts.get("severe", 0)
        
        if severe_count > 0:
            pattern = "dangerous"
        elif total >= 5:
            pattern = "problematic"
        elif total >= 2:
            pattern = "concerning"
        else:
            pattern = "minor"
        
        return {
            "total": total,
            "pattern": pattern,
            "severity_counts": severity_counts,
            "first_violation": strike_data.get("first_violation"),
            "last_violation": strike_data.get("last_violation"),
            "time_span_hours": (
                (strike_data.get("last_violation", 0) - 
                 strike_data.get("first_violation", 0)) / 3600
                if strike_data.get("first_violation") else 0
            )
        }
    
    def get_guild_statistics(self, guild_id: int) -> dict:
        """Get overall statistics for a guild"""
        guild_users = [
            (key, data) for key, data in self.strikes.items() 
            if key[0] == guild_id
        ]
        
        if not guild_users:
            return {
                "total_users_with_strikes": 0,
                "total_strikes": 0,
                "active_cases": 0,
                "top_violators": []
            }
        
        now = time.time()
        active_cases = sum(
            1 for _, data in guild_users 
            if now <= data.get("reset_at", 0)
        )
        
        total_strikes = sum(data.get("count", 0) for _, data in guild_users)
        
        # Top violators (by current strike count)
        top_violators = sorted(
            [(key[1], data.get("count", 0)) for key, data in guild_users],
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        return {
            "total_users_with_strikes": len(guild_users),
            "total_strikes": total_strikes,
            "active_cases": active_cases,
            "top_violators": top_violators
        }
    
    def cleanup_expired_strikes(self):
        """Remove expired strike records to save memory"""
        now = time.time()
        expired_keys = [
            key for key, data in self.strikes.items()
            if now > data.get("reset_at", 0) and data.get("count", 0) == 0
        ]
        
        for key in expired_keys:
            del self.strikes[key]
        
        return len(expired_keys)
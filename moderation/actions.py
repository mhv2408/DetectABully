"""
Moderation actions - timeouts, kicks, warnings, etc.
"""

import discord
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from config.settings import STRIKE_ESCALATION, PUNISHMENT_DURATIONS

class ModerationActions:
    """Handles all moderation actions and punishments"""
    
    def __init__(self):
        pass
    
    async def send_dm_warning(self, user: discord.User | discord.Member, 
                            level: str, reason: str, strike_count: int) -> bool:
        """
        Send a DM warning to the user
        
        Returns:
            bool: True if DM was sent successfully
        """
        try:
            dm_messages = {
                "warn": f"⚠️ **Warning**: {reason}\nPlease follow the server rules. (Strike {strike_count})",
                "flag": f"🚫 Your message was removed for: {reason}\nRepeated violations may result in timeout. (Strike {strike_count})",
                "severe": f"🛑 **Serious violation**: {reason}\nYour message was removed and action was taken. (Strike {strike_count})"
            }
            
            dm_content = dm_messages.get(level, f"Please follow server rules. Reason: {reason}")
            
            dm_channel = await user.create_dm()
            await dm_channel.send(dm_content)
            return True
            
        except discord.Forbidden:
            return False
        except Exception as e:
            print(f"DM error: {e}")
            return False
        
    
    
    async def timeout_user(self, member: discord.Member, duration_minutes: int, 
                          reason: str) -> Dict[str, Any]:
        """
        Timeout a user for specified duration
        
        Returns:
            Dict with action result information
        """
        try:
            until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
            await member.timeout(until, reason=reason)
            
            return {
                "success": True,
                "action": "timeout",
                "duration": duration_minutes,
                "reason": reason,
                "until": until
            }
            
        except discord.Forbidden:
            return {
                "success": False,
                "action": "timeout_failed",
                "error": "Missing timeout permissions"
            }
        except Exception as e:
            return {
                "success": False,
                "action": "timeout_failed", 
                "error": str(e)
            }
    
    async def kick_user(self, member: discord.Member, reason: str) -> Dict[str, Any]:
        """
        Kick a user from the server
        
        Returns:
            Dict with action result information
        """
        try:
            await member.kick(reason=reason)
            
            return {
                "success": True,
                "action": "kick",
                "reason": reason
            }
            
        except discord.Forbidden:
            return {
                "success": False,
                "action": "kick_failed",
                "error": "Missing kick permissions"
            }
        except Exception as e:
            return {
                "success": False,
                "action": "kick_failed",
                "error": str(e)
            }
    
    async def delete_message(self, message: discord.Message) -> bool:
        """
        Delete a message
        
        Returns:
            bool: True if message was deleted successfully
        """
        try:
            await message.delete()
            return True
        except discord.Forbidden:
            return False
        except discord.NotFound:
            return True  # Message already deleted
        except Exception:
            return False
    
    def get_escalated_punishment(self, strike_count: int, base_level: str) -> Dict[str, Any]:
        """
        Determine punishment based on strike count and violation level
        
        Returns:
            Dict with punishment details
        """
        # Check if we have specific escalation rules
        if strike_count in STRIKE_ESCALATION:
            escalation = STRIKE_ESCALATION[strike_count]
            return {
                "action": escalation["action"],
                "duration": escalation["duration"],
                "escalated": True
            }
        
        # Default escalation logic
        if base_level == "warn":
            if strike_count >= 5:
                return {"action": "timeout", "duration": 60, "escalated": True}
            elif strike_count >= 3:
                return {"action": "timeout", "duration": 15, "escalated": True}
            else:
                return {"action": "warn", "duration": 0, "escalated": False}
        
        elif base_level == "flag":
            if strike_count >= 4:
                return {"action": "kick", "duration": 0, "escalated": True}
            elif strike_count >= 2:
                return {"action": "timeout", "duration": 60 * strike_count, "escalated": True}
            else:
                return {"action": "timeout", "duration": 15, "escalated": False}
        
        elif base_level == "severe":
            if strike_count >= 2:
                return {"action": "kick", "duration": 0, "escalated": True}
            else:
                return {"action": "timeout", "duration": 240, "escalated": False}
        
        return {"action": "warn", "duration": 0, "escalated": False}
    
    async def handle_violation(self, message: discord.Message, level: str, 
                             reason: str, strike_count: int) -> Dict[str, Any]:
        """
        Handle a moderation violation with appropriate actions
        
        Returns:
            Dict with complete action results
        """
        results = {
            "message_deleted": False,
            "dm_sent": False,
            "punishment_applied": False,
            "punishment_details": {},
            "errors": []
        }
        
        try:
            # Get escalated punishment
            punishment = self.get_escalated_punishment(strike_count, level)
            
            # Delete message for flag and severe violations
            if level in ["flag", "severe"]:
                results["message_deleted"] = await self.delete_message(message)
                if not results["message_deleted"]:
                    results["errors"].append("Failed to delete message")
            
            # Send DM warning
            results["dm_sent"] = await self.send_dm_warning(
                message.author, level, reason, strike_count
            )
            
            # Apply punishment
            if punishment["action"] == "timeout" and punishment["duration"] > 0:
                try:
                    member = await message.guild.fetch_member(message.author.id)
                    timeout_result = await self.timeout_user(
                        member, punishment["duration"], f"{reason} (Strike {strike_count})"
                    )
                    results["punishment_applied"] = timeout_result["success"]
                    results["punishment_details"] = timeout_result
                    
                    if not timeout_result["success"]:
                        results["errors"].append(f"Timeout failed: {timeout_result.get('error', 'Unknown')}")
                        
                except discord.NotFound:
                    results["errors"].append("User not found in guild")
                
            elif punishment["action"] == "kick":
                try:
                    member = await message.guild.fetch_member(message.author.id)
                    kick_result = await self.kick_user(
                        member, f"Multiple violations: {reason}"
                    )
                    results["punishment_applied"] = kick_result["success"]
                    results["punishment_details"] = kick_result
                    
                    if not kick_result["success"]:
                        results["errors"].append(f"Kick failed: {kick_result.get('error', 'Unknown')}")
                        
                except discord.NotFound:
                    results["errors"].append("User not found in guild")
            
            else:
                # Just warning
                results["punishment_applied"] = True
                results["punishment_details"] = {"action": "warning"}
            
            # Add escalation info
            results["escalated"] = punishment.get("escalated", False)
            results["strike_count"] = strike_count
            
        except Exception as e:
            results["errors"].append(f"General error: {str(e)}")
        
        return results
    
    def format_action_summary(self, results: Dict[str, Any]) -> str:
        """
        Create a human-readable summary of actions taken
        
        Returns:
            str: Formatted action summary
        """
        actions = []
        
        if results.get("message_deleted"):
            actions.append("Message deleted")
        
        if results.get("dm_sent"):
            actions.append("DM warning sent")
        elif "dm_sent" in results:
            actions.append("DM warning failed")
        
        punishment = results.get("punishment_details", {})
        if punishment.get("action") == "timeout":
            duration = punishment.get("duration", 0)
            actions.append(f"Timeout: {duration}min")
        elif punishment.get("action") == "kick":
            actions.append("User kicked")
        elif punishment.get("action") == "warning":
            actions.append("Warning issued")
        
        if results.get("escalated"):
            actions.append("(Escalated)")
        
        if results.get("errors"):
            actions.append(f"Errors: {', '.join(results['errors'])}")
        
        return " | ".join(actions) if actions else "No actions taken"
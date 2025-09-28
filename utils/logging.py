"""
Enhanced logging system with Discord embeds
"""

import discord
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from config.settings import MOD_LOG_CHANNEL_ID

class ModLogger:
    """Handles moderation logging with rich embeds"""
    
    def __init__(self):
        self.color_map = {
            "warn": discord.Color.yellow(),
            "flag": discord.Color.orange(),
            "severe": discord.Color.red(),
            "info": discord.Color.blue(),
            "success": discord.Color.green()
        }
    
    async def get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Get the moderation log channel"""
        if MOD_LOG_CHANNEL_ID == 0:
            return None
        
        try:
            channel = guild.get_channel(MOD_LOG_CHANNEL_ID)
            if not channel:
                channel = await guild.fetch_channel(MOD_LOG_CHANNEL_ID)
            return channel
        except Exception as e:
            print(f"[mod-log] Error getting channel: {e}")
            return None
    
    def create_moderation_embed(self, user: discord.User, channel: discord.TextChannel,
                              level: str, reason: str, strike_count: int,
                              action_results: Dict[str, Any]) -> discord.Embed:
        """Create a rich embed for moderation logs"""
        
        embed = discord.Embed(
            title=f"🛡️ Moderation Action - {level.upper()}",
            color=self.color_map.get(level, discord.Color.dark_grey()),
            timestamp=datetime.now(timezone.utc)
        )
        
        # User information
        embed.add_field(
            name="👤 User",
            value=f"{user.mention} (`{user.id}`)\n{user.display_name}",
            inline=True
        )
        
        # Channel and strike info
        embed.add_field(
            name="📍 Channel",
            value=channel.mention,
            inline=True
        )
        
        embed.add_field(
            name="⚠️ Strikes",
            value=f"{strike_count} {'(Escalated)' if action_results.get('escalated') else ''}",
            inline=True
        )
        
        # Violation details
        embed.add_field(
            name="🔍 Violation",
            value=f"**Level:** {level}\n**Reason:** {reason}",
            inline=False
        )
        
        # Action taken
        punishment = action_results.get("punishment_details", {})
        action_text = self._format_action_text(action_results, punishment)
        embed.add_field(
            name="⚖️ Action Taken",
            value=action_text,
            inline=False
        )
        
        # Add user avatar
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        
        # Add footer with bot info
        embed.set_footer(text="ModBot Auto-Moderation", icon_url=None)
        
        return embed
    
    def _format_action_text(self, results: Dict[str, Any], 
                           punishment: Dict[str, Any]) -> str:
        """Format the action taken text for embed"""
        actions = []
        
        if results.get("message_deleted"):
            actions.append("🗑️ Message deleted")
        
        if results.get("dm_sent"):
            actions.append("📨 DM warning sent")
        elif "dm_sent" in results and not results["dm_sent"]:
            actions.append("📨 DM warning failed (user has DMs disabled)")
        
        # Punishment details
        if punishment.get("action") == "timeout":
            duration = punishment.get("duration", 0)
            actions.append(f"⏱️ Timeout: {duration} minutes")
        elif punishment.get("action") == "kick":
            actions.append("👢 User kicked from server")
        elif punishment.get("action") == "warning":
            actions.append("⚠️ Warning issued")
        
        # Errors
        errors = results.get("errors", [])
        if errors:
            actions.append(f"❌ Errors: {', '.join(errors)}")
        
        return "\n".join(actions) if actions else "No actions taken"
    
    async def log_moderation_action(self, guild: discord.Guild, user: discord.User,
                                  channel: discord.TextChannel, level: str, reason: str,
                                  strike_count: int, action_results: Dict[str, Any],
                                  analysis: Dict[str, Any] = None):
        """Log a moderation action with detailed information"""
        
        log_channel = await self.get_log_channel(guild)
        if not log_channel:
            print(f"[mod-log] No log channel configured for {guild.name}")
            return
        
        try:
            # Create main embed
            embed = self.create_moderation_embed(
                user, channel, level, reason, strike_count, action_results
            )
            
            # Add AI analysis if available
            if analysis:
                self._add_analysis_to_embed(embed, analysis)
            
            await log_channel.send(embed=embed)
            
        except discord.Forbidden:
            print(f"[mod-log] No permission to send to log channel in {guild.name}")
        except Exception as e:
            print(f"[mod-log] Error logging action: {e}")
    
    def _add_analysis_to_embed(self, embed: discord.Embed, analysis: Dict[str, Any]):
        """Add AI analysis details to the embed"""
        
        perspective = analysis.get("perspective", {})
        openai = analysis.get("openai", {})
        
        analysis_text = []
        
        # Perspective API results
        if perspective.get("score", 0) > 0:
            score = perspective["score"]
            analysis_text.append(f"**Perspective:** {score:.2f}")
            
            # Add top scoring categories
            details = perspective.get("details", {})
            if details:
                top_categories = sorted(
                    [(k, v) for k, v in details.items() if v > 0.3],
                    key=lambda x: x[1],
                    reverse=True
                )[:2]
                
                if top_categories:
                    cat_text = ", ".join([f"{k.lower()}: {v:.2f}" for k, v in top_categories])
                    analysis_text.append(f"**Categories:** {cat_text}")
        
        # OpenAI results
        if openai.get("flagged"):
            flagged_categories = [
                k for k, v in openai.get("categories", {}).items() if v
            ]
            if flagged_categories:
                analysis_text.append(f"**OpenAI:** {', '.join(flagged_categories[:3])}")
        
        if analysis_text:
            embed.add_field(
                name="🤖 AI Analysis",
                value="\n".join(analysis_text),
                inline=False
            )
    
    async def log_system_event(self, guild: discord.Guild, event_type: str, 
                             message: str, level: str = "info"):
        """Log system events (channel moderation toggled, etc.)"""
        
        log_channel = await self.get_log_channel(guild)
        if not log_channel:
            return
        
        try:
            embed = discord.Embed(
                title=f"📊 System Event - {event_type}",
                description=message,
                color=self.color_map.get(level, discord.Color.blue()),
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.set_footer(text="ModBot System")
            await log_channel.send(embed=embed)
            
        except Exception as e:
            print(f"[system-log] Error: {e}")
    
    async def log_message_content(self, guild: discord.Guild, user: discord.User,
                                channel: discord.TextChannel, content: str,
                                level: str):
        """Log the actual message content (for severe violations)"""
        
        log_channel = await self.get_log_channel(guild)
        if not log_channel:
            return
        
        try:
            embed = discord.Embed(
                title="📝 Message Content",
                color=self.color_map.get(level, discord.Color.red()),
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(
                name="User",
                value=f"{user.mention} in {channel.mention}",
                inline=False
            )
            
            # Truncate very long messages
            truncated_content = content[:1000] + "..." if len(content) > 1000 else content
            
            embed.add_field(
                name="Content",
                value=f"```{truncated_content}```",
                inline=False
            )
            
            if len(content) > 1000:
                embed.add_field(
                    name="Note",
                    value="Message was truncated for display",
                    inline=False
                )
            
            await log_channel.send(embed=embed)
            
        except Exception as e:
            print(f"[content-log] Error: {e}")
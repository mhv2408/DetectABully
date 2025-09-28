"""
Discord slash commands for the moderation bot
"""

import discord
from discord import app_commands
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.client import ModerationBot

from config.settings import MOD_FLAG

def setup_commands(tree: app_commands.CommandTree, bot: 'ModerationBot'):
    """Setup all slash commands"""
    
    @tree.command(name="moderate_here", description=f"Toggle moderation for this channel")
    async def moderate_here(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Administrator permissions required.", ephemeral=True
            )

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "❌ This command only works in text channels.", ephemeral=True
            )

        topic = channel.topic or ""
        try:
            if bot._topic_has_flag(topic):
                # Remove moderation
                new_topic = topic.replace(MOD_FLAG, "").strip()
                await channel.edit(topic=new_topic or None)
                bot.remove_moderated_channel(channel.id)
                msg = f"✅ **Moderation disabled** for {channel.mention}"
                
                # Log system event
                await bot.logger.log_system_event(
                    interaction.guild, "Moderation Disabled", 
                    f"{interaction.user.mention} disabled moderation in {channel.mention}"
                )
            else:
                # Add moderation
                sep = " " if topic and not topic.endswith(" ") else ""
                new_topic = f"{topic}{sep}{MOD_FLAG}".strip()
                await channel.edit(topic=new_topic)
                bot.add_moderated_channel(channel.id)
                msg = f"✅ **Moderation enabled** for {channel.mention}"
                
                # Log system event
                await bot.logger.log_system_event(
                    interaction.guild, "Moderation Enabled",
                    f"{interaction.user.mention} enabled moderation in {channel.mention}",
                    "success"
                )
            
            await interaction.response.send_message(msg, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Missing **Manage Channels** permission.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @tree.command(name="mod_status", description="Show moderation status and statistics")
    async def mod_status(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛡️ Moderation Status",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Moderated channels
        channel_mentions = []
        for channel_id in sorted(bot.moderated_channels):
            channel = interaction.guild.get_channel(channel_id)
            channel_mentions.append(channel.mention if channel else f"`{channel_id}`")
        
        channels_text = "\n".join(channel_mentions) if channel_mentions else "None"
        embed.add_field(name="Moderated Channels", value=channels_text, inline=False)
        
        # Guild statistics
        guild_stats = bot.strikes.get_guild_statistics(interaction.guild.id)
        embed.add_field(name="Active Cases", value=str(guild_stats["active_cases"]), inline=True)
        embed.add_field(name="Total Users", value=str(guild_stats["total_users_with_strikes"]), inline=True)
        embed.add_field(name="Total Strikes", value=str(guild_stats["total_strikes"]), inline=True)
        
        # Top violators (if any)
        if guild_stats["top_violators"]:
            violators_text = []
            for user_id, count in guild_stats["top_violators"][:3]:
                user = interaction.guild.get_member(user_id)
                name = user.display_name if user else f"User {user_id}"
                violators_text.append(f"{name}: {count}")
            
            embed.add_field(
                name="Top Violators",
                value="\n".join(violators_text),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(name="whitelist", description="Add/remove user from moderation whitelist")
    async def whitelist_user(interaction: discord.Interaction, user: discord.User, 
                           action: str):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Administrator permissions required.", ephemeral=True
            )
        
        if action.lower() == "add":
            bot.classifier.add_to_whitelist(user.id)
            await interaction.response.send_message(
                f"✅ Added {user.mention} to whitelist.", ephemeral=True
            )
            
            await bot.logger.log_system_event(
                interaction.guild, "Whitelist Updated",
                f"{interaction.user.mention} added {user.mention} to whitelist"
            )
            
        elif action.lower() == "remove":
            bot.classifier.remove_from_whitelist(user.id)
            await interaction.response.send_message(
                f"✅ Removed {user.mention} from whitelist.", ephemeral=True
            )
            
            await bot.logger.log_system_event(
                interaction.guild, "Whitelist Updated", 
                f"{interaction.user.mention} removed {user.mention} from whitelist"
            )
        else:
            await interaction.response.send_message(
                "❌ Action must be 'add' or 'remove'", ephemeral=True
            )

    @tree.command(name="user_strikes", description="Check strike count and history for a user")
    async def user_strikes(interaction: discord.Interaction, user: discord.User):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message(
                "❌ Manage Messages permission required.", ephemeral=True
            )
        
        strike_data = bot.strikes.get_strikes(interaction.guild.id, user.id)
        pattern = bot.strikes.get_violation_pattern(interaction.guild.id, user.id)
        
        embed = discord.Embed(
            title=f"📊 Strike Report: {user.display_name}",
            color=discord.Color.orange() if strike_data["count"] > 0 else discord.Color.green()
        )
        
        embed.add_field(name="Current Strikes", value=str(strike_data["count"]), inline=True)
        embed.add_field(name="Pattern", value=pattern["pattern"].title(), inline=True)
        embed.add_field(name="Total History", value=str(pattern["total"]), inline=True)
        
        # Recent violations
        if strike_data["history"]:
            recent = strike_data["history"][-5:]  # Last 5 strikes
            history_text = []
            for violation in recent:
                timestamp = f"<t:{int(violation['timestamp'])}:R>"
                severity = violation.get('severity', 'unknown')
                reason = violation.get('reason', 'No reason')[:50]
                history_text.append(f"**{severity.title()}**: {reason} ({timestamp})")
            
            embed.add_field(
                name="Recent Violations",
                value="\n".join(history_text),
                inline=False
            )
        else:
            embed.add_field(name="Status", value="Clean record ✅", inline=False)
        
        # Severity breakdown
        if pattern["severity_counts"]:
            severity_text = []
            for severity, count in pattern["severity_counts"].items():
                severity_text.append(f"{severity.title()}: {count}")
            
            embed.add_field(
                name="Violation Breakdown",
                value=" | ".join(severity_text),
                inline=False
            )
        
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(name="clear_strikes", description="Clear all strikes for a user")
    async def clear_strikes(interaction: discord.Interaction, user: discord.User):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Administrator permissions required.", ephemeral=True
            )
        
        cleared = bot.strikes.clear_strikes(interaction.guild.id, user.id)

        # Also remove active timeout if present
        member = interaction.guild.get_member(user.id)
        if member and member.communication_disabled_until:
            try:
                await member.edit(timed_out_until=None, reason="Strikes cleared")
            except discord.Forbidden:
                await interaction.followup.send("❌ Bot lacks permission to remove timeout.", ephemeral=True)
            except discord.HTTPException as e:
                await interaction.followup.send(f"❌ Failed to remove timeout: {e}", ephemeral=True)
        
        if cleared:
            await interaction.response.send_message(
                f"✅ Cleared all strikes for {user.mention}.", ephemeral=True
            )
            
            await bot.logger.log_system_event(
                interaction.guild, "Strikes Cleared",
                f"{interaction.user.mention} cleared strikes for {user.mention}"
            )
        else:
            await interaction.response.send_message(
                f"ℹ️ {user.mention} has no strikes to clear.", ephemeral=True
            )

    @tree.command(name="test_message", description="Test message classification (Admin only)")
    async def test_message(interaction: discord.Interaction, text: str):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Administrator permissions required.", ephemeral=True
            )
        
        await interaction.response.defer(ephemeral=True)
        
        # Classify the test message
        level, reason, analysis = await bot.classifier.classify_message(text, interaction.user.id)
        
        embed = discord.Embed(
            title="🧪 Message Classification Test",
            color=bot.logger.color_map.get(level, discord.Color.gray())
        )
        
        embed.add_field(name="Test Message", value=f"```{text[:500]}```", inline=False)
        embed.add_field(name="Classification", value=level.title(), inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)
        
        # Add AI analysis if available
        if analysis:
            perspective_score = analysis.get("perspective", {}).get("score", 0)
            openai_flagged = analysis.get("openai", {}).get("flagged", False)
            
            analysis_text = []
            if perspective_score > 0:
                analysis_text.append(f"**Perspective:** {perspective_score:.3f}")
            if openai_flagged:
                categories = [k for k, v in analysis.get("openai", {}).get("categories", {}).items() if v]
                analysis_text.append(f"**OpenAI:** {', '.join(categories[:3])}")
            
            if analysis_text:
                embed.add_field(
                    name="AI Analysis",
                    value="\n".join(analysis_text),
                    inline=False
                )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tree.command(name="cleanup_strikes", description="Clean up expired strike records")
    async def cleanup_strikes(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Administrator permissions required.", ephemeral=True
            )
        
        cleaned = bot.strikes.cleanup_expired_strikes()
        await interaction.response.send_message(
            f"✅ Cleaned up {cleaned} expired strike records.", ephemeral=True
        )

    @tree.command(name="bot_info", description="Show bot information and diagnostics")
    async def bot_info(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🤖 ModBot Information",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Bot stats
        embed.add_field(
            name="Bot Status",
            value=f"**Latency:** {bot.client.latency*1000:.0f}ms\n**Guilds:** {len(bot.client.guilds)}",
            inline=True
        )
        
        # Moderation stats
        total_moderated = len(bot.moderated_channels)
        embed.add_field(
            name="Moderation",
            value=f"**Channels:** {total_moderated}\n**Whitelist:** {len(bot.classifier.whitelist)}",
            inline=True
        )
        
        # API status (basic check)
        from config.settings import PERSPECTIVE_API_KEY, OPENAI_API_KEY
        api_status = []
        if PERSPECTIVE_API_KEY:
            api_status.append("✅ Perspective API")
        else:
            api_status.append("❌ Perspective API")
        
        if OPENAI_API_KEY:
            api_status.append("✅ OpenAI API")
        else:
            api_status.append("❌ OpenAI API")
        
        embed.add_field(
            name="AI Services",
            value="\n".join(api_status),
            inline=True
        )
        
        # Permission check for current guild
        if interaction.guild:
            me = interaction.guild.me
            perms = interaction.channel.permissions_for(me)
            
            perm_status = []
            perm_status.append(f"{'✅' if perms.manage_messages else '❌'} Manage Messages")
            perm_status.append(f"{'✅' if perms.moderate_members else '❌'} Moderate Members")
            perm_status.append(f"{'✅' if perms.kick_members else '❌'} Kick Members")
            perm_status.append(f"{'✅' if perms.manage_channels else '❌'} Manage Channels")
            
            embed.add_field(
                name="Permissions",
                value="\n".join(perm_status),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
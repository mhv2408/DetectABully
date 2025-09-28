"""
Discord slash commands for the moderation bot (DB-backed whitelist & strikes)
"""

import discord
from discord import app_commands
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.client import ModerationBot

from config.settings import MOD_FLAG

from data.whitelist_repo import wl_add, wl_remove, wl_count
from data.strikes_repo import (
    get_user_immunity, 
    get_immunity_leaderboard, 
    process_weekly_bonus,
    add_positive_points,
    strike_get,
    strike_clear,

)

# Optional: if you add it, we'll use it; otherwise we fallback
try:
    from data.strikes_repo import guild_stats  # async (guild_id) -> dict
except Exception:
    guild_stats = None  # type: ignore

def setup_commands(tree: app_commands.CommandTree, bot: 'ModerationBot'):
    """Setup all slash commands"""

    @tree.command(name="moderate_here", description="Toggle moderation for this channel")
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

    @tree.command(name="mod_status", description="Show moderation status and basic stats")
    async def mod_status(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛡️ Moderation Status",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )

        # Moderated channels
        channel_mentions = []
        for channel_id in sorted(bot.moderated_channels):
            ch = interaction.guild.get_channel(channel_id)
            channel_mentions.append(ch.mention if ch else f"`{channel_id}`")
        channels_text = "\n".join(channel_mentions) if channel_mentions else "None"
        embed.add_field(name="Moderated Channels", value=channels_text, inline=False)

        # Whitelist count (DB)
        try:
            wl_cnt = await wl_count(str(interaction.guild_id))
        except Exception:
            wl_cnt = "—"
        embed.add_field(name="Whitelisted Users", value=str(wl_cnt), inline=True)

        # Strike stats (optional DB helper)
        if guild_stats:
            try:
                gs = await guild_stats(str(interaction.guild_id))
                embed.add_field(name="Active Users With Strikes", value=str(gs.get("active_users", 0)), inline=True)
                embed.add_field(name="Total Strikes (current windows)", value=str(gs.get("total_strikes", 0)), inline=True)
            except Exception:
                embed.add_field(name="Active Users With Strikes", value="—", inline=True)
                embed.add_field(name="Total Strikes", value="—", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # Kept your single command with an action param for compatibility
    @tree.command(name="whitelist", description="Add/remove a user from the moderation whitelist")
    async def whitelist_user(
        interaction: discord.Interaction,
        user: discord.User,
        action: str,
        reason: str = ""
    ):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Administrator permissions required.", ephemeral=True
            )

        action_l = action.strip().lower()
        if action_l not in ("add", "remove"):
            return await interaction.response.send_message(
                "❌ Action must be 'add' or 'remove'.", ephemeral=True
            )

        try:
            if action_l == "add":
                res = await wl_add(
                    str(interaction.guild_id),
                    str(user.id),
                    reason or None,
                    str(interaction.user.id)
                )
                if res["inserted"]:
                    msg = f"✅ Added {user.mention} to whitelist."
                    log_title = "Whitelist Added"
                else:
                    msg = f"ℹ️ {user.mention} was already whitelisted — details updated."
                    log_title = "Whitelist Updated"

                await interaction.response.send_message(msg, ephemeral=True)

                # System log (non-ephemeral post to #mod-log via your logger)
                details = f"{interaction.user.mention} → {user.mention}"
                if reason:
                    details += f"\nReason: {reason}"
                await bot.logger.log_system_event(
                    interaction.guild, log_title, details, "success"
                )

            else:  # remove
                res = await wl_remove(str(interaction.guild_id), str(user.id))
                if res["removed"]:
                    msg = f"✅ Removed {user.mention} from whitelist."
                    log_title = "Whitelist Removed"
                else:
                    msg = f"ℹ️ {user.mention} was not on the whitelist."
                    log_title = "Whitelist Not Found"

                await interaction.response.send_message(msg, ephemeral=True)

                await bot.logger.log_system_event(
                    interaction.guild, log_title,
                    f"{interaction.user.mention} → {user.mention}"
                )

        except Exception as e:
            # If we haven’t responded yet, send an error; otherwise use followup
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ DB error: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ DB error: {e}", ephemeral=True)


    @tree.command(name="user_strikes", description="Check the current strike count for a user")
    async def user_strikes_cmd(interaction: discord.Interaction, user: discord.User):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message(
                "❌ Manage Messages permission required.", ephemeral=True
            )
        try:
            row = await strike_get(str(interaction.guild_id), str(user.id))
            cnt = int(row["count"]) if row else 0
            reset_at = int(row["reset_at"]) if row else None

            embed = discord.Embed(
                title=f"📊 Strike Report: {user.display_name}",
                color=discord.Color.orange() if cnt > 0 else discord.Color.green()
            )
            embed.add_field(name="Current Strikes", value=str(cnt), inline=True)
            if reset_at:
                embed.add_field(name="Window Resets", value=f"<t:{reset_at}:R>", inline=True)
            else:
                embed.add_field(name="Window Resets", value="—", inline=True)

            if user.avatar:
                embed.set_thumbnail(url=user.avatar.url)

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ DB error: {e}", ephemeral=True)

    @tree.command(name="clear_strikes", description="Clear all strikes for a user")
    async def clear_strikes_cmd(interaction: discord.Interaction, user: discord.User):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Administrator permissions required.", ephemeral=True
            )
        # Clear from DB
        try:
            await strike_clear(str(interaction.guild_id), str(user.id))
        except Exception as e:
            return await interaction.response.send_message(f"❌ DB error: {e}", ephemeral=True)

        # Try to remove any active timeout
        removed_timeout_note = ""
        member = interaction.guild.get_member(user.id)
        if member and member.communication_disabled_until:
            try:
                await member.edit(timed_out_until=None, reason="Strikes cleared")
                removed_timeout_note = "\nAlso removed active timeout."
            except discord.Forbidden:
                removed_timeout_note = "\n⚠️ Missing permission to remove timeout."
            except discord.HTTPException as e:
                removed_timeout_note = f"\n⚠️ Failed to remove timeout: {e}"

        await interaction.response.send_message(
            f"✅ Cleared all strikes for {user.mention}.{removed_timeout_note}",
            ephemeral=True
        )

        await bot.logger.log_system_event(
            interaction.guild, "Strikes Cleared",
            f"{interaction.user.mention} cleared strikes for {user.mention}"
        )

    @tree.command(name="test_message", description="Test message classification (Admin only)")
    async def test_message(interaction: discord.Interaction, text: str):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Administrator permissions required.", ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)

        level, reason, analysis = await bot.classifier.classify_message(text, interaction.user.id)

        embed = discord.Embed(
            title="🧪 Message Classification Test",
            color=bot.logger.color_map.get(level, discord.Color.gray())
        )
        embed.add_field(name="Test Message", value=f"```{text[:500]}```", inline=False)
        embed.add_field(name="Classification", value=level.title(), inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)

        if analysis:
            perspective_score = analysis.get("perspective", {}).get("score", 0)
            openai_flagged = analysis.get("openai", {}).get("flagged", False)
            analysis_text = []
            if perspective_score:
                analysis_text.append(f"**Perspective:** {perspective_score:.3f}")
            if openai_flagged:
                cats = [k for k, v in analysis.get("openai", {}).get("categories", {}).items() if v]
                if cats:
                    analysis_text.append(f"**OpenAI:** {', '.join(cats[:3])}")
            if analysis_text:
                embed.add_field(name="AI Analysis", value="\n".join(analysis_text), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @tree.command(name="cleanup_strikes", description="Clean up expired strike records")
    async def cleanup_strikes(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Administrator permissions required.", ephemeral=True
            )
        
        await interaction.response.defer(ephemeral=True)
        
        # Import the cleanup function from your strikes repo
        from data.strikes_repo import cleanup_expired_strikes
        
        cleaned = await cleanup_expired_strikes(str(interaction.guild.id))
        
        embed = discord.Embed(
            title="🧹 Strike Cleanup Complete",
            color=discord.Color.green()
        )
        
        if cleaned > 0:
            embed.description = f"Cleaned up {cleaned} expired strike records."
            embed.add_field(
                name="✅ Completed",
                value=f"• Removed {cleaned} expired records\n• Preserved records with positive points\n• Reset strike counts for good users",
                inline=False
            )
        else:
            embed.description = "No expired strike records found to clean up."
            embed.add_field(
                name="ℹ️ Status", 
                value="Database is already clean!",
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Log the cleanup
        try:
            await bot.logger.log_system_event(
                interaction.guild, "Strike Cleanup",
                f"{interaction.user.mention} cleaned up {cleaned} expired strike records",
                "info"
            )
        except Exception as e:
            print(f"Error logging cleanup: {e}")

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

        # Moderation
        total_moderated = len(bot.moderated_channels)
        try:
            wl_cnt = await wl_count(str(interaction.guild_id))
        except Exception:
            wl_cnt = "—"
        embed.add_field(
            name="Moderation",
            value=f"**Channels:** {total_moderated}\n**Whitelist:** {wl_cnt}",
            inline=True
        )

        # API status
        from config.settings import PERSPECTIVE_API_KEY, OPENAI_API_KEY
        api_status = []
        api_status.append("✅ Perspective API" if PERSPECTIVE_API_KEY else "❌ Perspective API")
        api_status.append("✅ OpenAI API" if OPENAI_API_KEY else "❌ OpenAI API")
        embed.add_field(name="AI Services", value="\n".join(api_status), inline=True)

        # Permission check for current channel
        if interaction.guild:
            me = interaction.guild.me
            perms = interaction.channel.permissions_for(me)
            perm_status = []
            perm_status.append(f"{'✅' if perms.manage_messages else '❌'} Manage Messages")
            perm_status.append(f"{'✅' if perms.moderate_members else '❌'} Moderate Members")
            perm_status.append(f"{'✅' if perms.kick_members else '❌'} Kick Members")
            perm_status.append(f"{'✅' if perms.manage_channels else '❌'} Manage Channels")
            embed.add_field(name="Permissions", value="\n".join(perm_status), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(name="user_immunity", description="Check user's immunity status and positive points")
    async def user_immunity(interaction: discord.Interaction, user: discord.User = None):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message(
                "❌ Manage Messages permission required.", ephemeral=True
            )
        
        target_user = user or interaction.user
        immunity = await get_user_immunity(str(interaction.guild.id), str(target_user.id))
        
        # Create embed with immunity status
        embed = discord.Embed(
            title=f"🛡️ Community Immunity Status: {target_user.display_name}",
        )
        
        # Immunity level with emoji
        level_emojis = {
            "none": "⚪ None",
            "trusted": "🟢 Trusted Member", 
            "veteran": "🔵 Veteran Guardian",
            "guardian": "🟣 Community Guardian"
        }
        
        embed.add_field(
            name="Immunity Level", 
            value=level_emojis.get(immunity["immunity_level"], "❓ Unknown"),
            inline=True
        )
        
        embed.add_field(
            name="Positive Points",
            value=f"{immunity['positive_points']:,}",
            inline=True
        )
        
        embed.add_field(
            name="Current Strikes", 
            value=str(immunity["strikes"]),
            inline=True
        )
        
        # Show what they can bypass
        bypass_abilities = []
        if immunity["can_bypass_warnings"]:
            bypass_abilities.append("✅ Minor warnings")
        if immunity["can_bypass_minor_flags"]:
            bypass_abilities.append("✅ Moderate flags")  
        if immunity["can_bypass_all_but_severe"]:
            bypass_abilities.append("✅ All but severe violations")
        
        if bypass_abilities:
            embed.add_field(
                name="🛡️ Can Bypass",
                value="\n".join(bypass_abilities),
                inline=False
            )
        else:
            embed.add_field(
                name="🛡️ Bypass Abilities", 
                value="No immunity protections",
                inline=False
            )
        
        # Next threshold
        if immunity["next_threshold"]:
            points_needed = immunity["next_threshold"] - immunity["positive_points"]
            embed.add_field(
                name="📈 Next Level",
                value=f"Need {points_needed:,} more points",
                inline=True
            )
        else:
            embed.add_field(
                name="📈 Status",
                value="🎉 Maximum level achieved!",
                inline=True
            )
        
        if target_user.avatar:
            embed.set_thumbnail(url=target_user.avatar.url)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(name="immunity_leaderboard", description="Show top community members by positive points")
    async def immunity_leaderboard(interaction: discord.Interaction, limit: int = 10):
        if limit > 20:
            limit = 20
        
        leaderboard = await get_immunity_leaderboard(str(interaction.guild.id), limit)
        
        if not leaderboard:
            embed = discord.Embed(
                title="🏆 Community Immunity Leaderboard",
                description="No positive points recorded yet!",
                color=discord.Color.blue()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        embed = discord.Embed(
            title="🏆 Community Immunity Leaderboard", 
            description=f"Top {len(leaderboard)} members by positive behavior",
            color=discord.Color.gold()
        )
        
        leaderboard_text = []
        for i, entry in enumerate(leaderboard, 1):
            user = interaction.guild.get_member(int(entry["user_id"]))
            name = user.display_name if user else f"User {entry['user_id']}"
            
            level_emoji = {
                "guardian": "🟣",
                "veteran": "🔵", 
                "trusted": "🟢",
                "none": "⚪"
            }.get(entry["immunity_level"], "❓")
            
            points = entry["positive_points"]
            strikes = entry["count"] or 0
            
            leaderboard_text.append(
                f"**{i}.** {level_emoji} {name}\n"
                f"     💎 {points:,} points • ⚠️ {strikes} strikes"
            )
        
        embed.add_field(
            name="Rankings",
            value="\n".join(leaderboard_text),
            inline=False
        )
        
        embed.set_footer(text="Earn points through positive behavior!")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(name="award_points", description="Manually award positive points to a user")
    async def award_points(interaction: discord.Interaction, user: discord.User, points: int, reason: str = None):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Administrator permissions required.", ephemeral=True
            )
        
        if points < 1 or points > 100:
            return await interaction.response.send_message(
                "❌ Points must be between 1 and 100.", ephemeral=True
            )
        
        await add_positive_points(
            str(interaction.guild.id), 
            str(user.id), 
            points, 
            reason or f"Manual award by {interaction.user.display_name}"
        )
        
        # Get updated immunity status
        immunity = await get_user_immunity(str(interaction.guild.id), str(user.id))
        
        embed = discord.Embed(
            title="✨ Positive Points Awarded!",
            color=discord.Color.green()
        )
        
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(name="Points Awarded", value=f"+{points}", inline=True) 
        embed.add_field(name="New Total", value=f"{immunity['positive_points']:,}", inline=True)
        
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        
        # Show if they gained immunity level
        level_emojis = {
            "trusted": "🟢 Trusted Member",
            "veteran": "🔵 Veteran Guardian", 
            "guardian": "🟣 Community Guardian"
        }
        
        if immunity["immunity_level"] != "none":
            embed.add_field(
                name="🛡️ Immunity Level",
                value=level_emojis.get(immunity["immunity_level"], immunity["immunity_level"]),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Log the manual award
        await bot.logger.log_system_event(
            interaction.guild, "Manual Points Award",
            f"{interaction.user.mention} awarded {points} points to {user.mention}. Reason: {reason or 'No reason given'}",
            "success"
        )

    @tree.command(name="weekly_bonus", description="Award weekly bonuses to well-behaved users")
    async def weekly_bonus(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Administrator permissions required.", ephemeral=True
            )
        
        await interaction.response.defer(ephemeral=True)
        
        awarded_users = await process_weekly_bonus(str(interaction.guild.id))
        
        if not awarded_users:
            embed = discord.Embed(
                title="📅 Weekly Bonus Check",
                description="No users qualified for weekly bonuses at this time.",
                color=discord.Color.blue()
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        embed = discord.Embed(
            title="🎉 Weekly Bonuses Awarded!",
            description=f"Awarded bonuses to {len(awarded_users)} well-behaved members",
            color=discord.Color.green()
        )
        
        bonus_text = []
        for award in awarded_users[:10]:  # Show max 10
            user = interaction.guild.get_member(int(award["user_id"]))
            name = user.display_name if user else f"User {award['user_id']}"
            
            bonus_text.append(
                f"🎁 **{name}**\n"
                f"   +{award['points_awarded']} points → {award['total_points']:,} total"
            )
        
        embed.add_field(
            name="Recipients",
            value="\n".join(bonus_text),
            inline=False
        )
        
        if len(awarded_users) > 10:
            embed.add_field(
                name="Additional",
                value=f"...and {len(awarded_users) - 10} more members received bonuses!",
                inline=False
            )
        
        embed.set_footer(text="Weekly bonuses encourage consistent good behavior!")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Also send a summary to mod log if configured
        try:
            summary = f"🎉 **Weekly Bonus Round Complete**\n"
            summary += f"• **{len(awarded_users)} members** received bonuses\n" 
            summary += f"• **Total points awarded:** {sum(a['points_awarded'] for a in awarded_users):,}\n"
            summary += f"• **Processed by:** {interaction.user.mention}"
            
            await bot.logger.log_system_event(
                interaction.guild, "Weekly Bonuses Awarded",
                summary, "success"
            )
        except Exception as e:
            print(f"Error logging weekly bonus: {e}")

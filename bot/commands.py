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

# NEW: import DB repos
from data.whitelist_repo import wl_add, wl_remove, wl_count
from data.strikes_repo import strike_get, strike_clear, cleanup_expired_strikes
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

    @tree.command(name="cleanup_strikes", description="Delete expired strike records (DB)")
    async def cleanup_strikes_cmd(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Administrator permissions required.", ephemeral=True
            )
        try:
            cleaned = await cleanup_expired_strikes(str(interaction.guild_id))
        except Exception as e:
            return await interaction.response.send_message(f"❌ DB error: {e}", ephemeral=True)

        await interaction.response.send_message(
            f"✅ Cleaned up **{cleaned}** expired strike records.", ephemeral=True
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

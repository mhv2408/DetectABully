# main.py
import os, re, time
from datetime import datetime, timedelta, timezone
import asyncio
from dotenv import load_dotenv
import discord
from discord import app_commands

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
MOD_LOG_CHANNEL_ID = int(os.getenv("MOD_LOG_CHANNEL_ID", "0"))

# ---------- Intents ----------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
# (No members intent needed; we'll fetch member via HTTP when needed.)

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# ---------- Config / State ----------
MOD_FLAG = "[modbot]"                 # marker in channel topic
moderated_channels = set()            # channel IDs detected from topic at boot
strikes = {}                          # (guild_id, user_id) -> {"count": int, "reset_at": ts}

# ---------- Rules ----------
SLUR_RE = re.compile(r"(?i)\b(stupid|idiot|moron|kys|retard)\b")

def is_caps_spam(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 12: return False
    caps = sum(1 for c in letters if c.isupper())
    return caps / max(1, len(letters)) > 0.7

def is_targeted_insult(text: str) -> bool:
    return ("<@" in text or "@" in text) and SLUR_RE.search(text) is not None

def classify_message(text: str):
    """Return (level, reason). levels: none | warn | flag | severe"""
    t = text.strip()
    if not t: return ("none", "")
    if SLUR_RE.search(t):     return ("severe", "slur detected")
    if is_targeted_insult(t): return ("flag",   "targeted insult")
    if is_caps_spam(t):       return ("warn",   "excessive shouting")
    return ("none", "")

# ---------- Helpers ----------
async def dm_user(user: discord.User | discord.Member, content: str):
    try:
        dm = await user.create_dm()
        await dm.send(content)
    except Exception:
        pass

async def log_mod(guild: discord.Guild, content: str):
    if MOD_LOG_CHANNEL_ID == 0:
        print("[mod-log] Not configured"); return
    try:
        ch = guild.get_channel(MOD_LOG_CHANNEL_ID) or await guild.fetch_channel(MOD_LOG_CHANNEL_ID)
        await ch.send(content)
    except discord.Forbidden:
        print("[mod-log] 403 Missing Access – fix channel perms for the bot")
    except Exception as e:
        print(f"[mod-log] error: {e}")

def bump_strike(guild_id: int, user_id: int, window_minutes: int = 60) -> int:
    key = (guild_id, user_id)
    now = time.time()
    entry = strikes.get(key, {"count": 0, "reset_at": now + window_minutes*60})
    if now > entry["reset_at"]:
        entry = {"count": 0, "reset_at": now + window_minutes*60}
    entry["count"] += 1
    strikes[key] = entry
    return entry["count"]

def topic_has_flag(topic: str | None) -> bool:
    return bool(topic) and MOD_FLAG.lower() in topic.lower()

# ---------- Slash commands ----------
@tree.command(name="moderate_here", description=f"Toggle moderation for this channel (adds/removes {MOD_FLAG} in topic)")
async def moderate_here(inter: discord.Interaction):
    if not inter.user.guild_permissions.manage_guild:
        return await inter.response.send_message("Admins only.", ephemeral=True)

    # Ensure we’re in a text channel
    ch = inter.channel
    if not isinstance(ch, discord.TextChannel):
        return await inter.response.send_message("Run this in a text channel.", ephemeral=True)

    topic = ch.topic or ""
    try:
        if topic_has_flag(topic):
            # remove flag
            new_topic = topic.replace(MOD_FLAG, "")
            new_topic = " ".join(new_topic.split())  # tidy spaces
            await ch.edit(topic=new_topic or None)
            moderated_channels.discard(ch.id)
            msg = f"✅ Disabled moderation here. (Removed {MOD_FLAG} from topic)"
        else:
            # add flag
            sep = "" if (not topic or topic.endswith(" ")) else " "
            new_topic = (topic or "") + f"{sep}{MOD_FLAG}"
            await ch.edit(topic=new_topic)
            moderated_channels.add(ch.id)
            msg = f"✅ Enabled moderation here. (Added {MOD_FLAG} to topic)"
        await inter.response.send_message(msg, ephemeral=True)
    except discord.Forbidden:
        await inter.response.send_message(
            "❌ I need **Manage Channels** permission to edit the topic here.",
            ephemeral=True
        )
    except Exception as e:
        await inter.response.send_message(f"❌ Failed to toggle: {e}", ephemeral=True)

@tree.command(name="mod_status", description="Show which channels are moderated (topic contains the mod flag)")
async def mod_status(inter: discord.Interaction):
    names = []
    for cid in sorted(moderated_channels):
        ch = inter.guild.get_channel(cid)
        names.append(f"<#{cid}>" if ch else str(cid))
    txt = "Moderated: " + (", ".join(names) if names else "None")
    await inter.response.send_message(txt, ephemeral=True)

@tree.command(name="diag", description="Bot diagnostics")
async def diag(inter: discord.Interaction):
    if not inter.user.guild_permissions.manage_guild:
        return await inter.response.send_message("Admins only.", ephemeral=True)
    # Check mod-log perms quickly
    modlog = "n/a"
    try:
        ch = inter.guild.get_channel(MOD_LOG_CHANNEL_ID) or await inter.guild.fetch_channel(MOD_LOG_CHANNEL_ID)
        perms = ch.permissions_for(inter.guild.me)
        modlog = f"view={perms.view_channel}, send={perms.send_messages}, read_hist={perms.read_message_history}"
    except Exception as e:
        modlog = f"error: {e}"
    chans = ", ".join(f"<#{c}>" for c in moderated_channels) or "None"
    await inter.response.send_message(
        f"Intents: message_content={bot.intents.message_content}\n"
        f"Moderated: {chans}\n"
        f"mod-log perms: {modlog}",
        ephemeral=True
    )

# ---------- Events ----------
@bot.event
async def on_ready():
    # Rebuild moderated_channels by scanning topics
    moderated_channels.clear()
    for g in bot.guilds:
        for ch in g.text_channels:
            if topic_has_flag(ch.topic):
                moderated_channels.add(ch.id)
    try:
        await tree.sync()
    except Exception:
        pass
    print(f"Logged in as {bot.user} (latency {bot.latency:.3f}s)")
    print(f"[boot] Moderating {len(moderated_channels)} channels: {sorted(moderated_channels)}")

@bot.event
async def on_message(message: discord.Message):
    # ignore self/bots
    if message.author.bot: return
    if message.guild is None: return
    if message.channel.id not in moderated_channels: return

    level, reason = classify_message(message.content)
    if level == "none":
        return

    count = bump_strike(message.guild.id, message.author.id)
    why = (
        f"**User:** <@{message.author.id}>\n"
        f"**Channel:** <#{message.channel.id}>\n"
        f"**Level:** {level} (strike {count})\n"
        f"**Reason:** {reason}\n"
        f"**Excerpt:** {message.content[:180]}"
    )

    action_note = ""
    try:
        if level == "warn":
            await dm_user(message.author, f"Please keep it respectful. Reason: {reason}")
            action_note = "DM warn"
        elif level == "flag":
            await message.delete()
            await dm_user(message.author, "Your message was removed for targeted harassment.")
            action_note = "Deleted + warned"
        elif level == "severe":
            await message.delete()
            member = await message.guild.fetch_member(message.author.id)
            until = datetime.now(timezone.utc) + timedelta(minutes=30)
            try:
                await member.timeout(until, reason="Severe harassment")  # positional 'until'
                action_note = "Deleted + 30m timeout"
            except discord.Forbidden:
                # fallback to kick if timeout not permitted
                try:
                    await member.kick(reason="Severe harassment")
                    action_note = "Deleted + KICKED (timeout not permitted)"
                except discord.Forbidden:
                    action_note = "Deleted (no timeout/kick perms)"
    except discord.Forbidden:
        action_note = "FAILED (missing permission)"
    except Exception as e:
        action_note = f"ERROR {e}"

    await log_mod(message.guild, why + f"\n_Action_: {action_note}")

# ---------- Run ----------
if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Set DISCORD_BOT_TOKEN in .env")
    bot.run(TOKEN)

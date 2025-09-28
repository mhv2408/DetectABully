import os, re, time
from datetime import datetime, timedelta
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

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# ---------- Config / State (MVP: in-memory) ----------
moderated_channels = set()  # channel IDs
# strikes[(guild_id, user_id)] = {"count": int, "reset_at": timestamp}
strikes = {}

# Basic rules (extend later)
SLUR_RE = re.compile(r"(?i)\b(stupid|idiot|moron|kys|retard)\b")
def is_caps_spam(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 12: return False
    caps = sum(1 for c in letters if c.isupper())
    return caps / max(1, len(letters)) > 0.7

def is_targeted_insult(text: str) -> bool:
    # naive: insult + an @mention in the same message
    return ("<@" in text or "@" in text) and SLUR_RE.search(text) is not None

def classify_message(text: str):
    """Return (level, reason). levels: none | warn | flag | severe"""
    t = text.strip()
    if not t: return ("none", "")
    if SLUR_RE.search(t):    return ("severe", "slur detected")
    if is_targeted_insult(t):return ("flag",   "targeted insult")
    if is_caps_spam(t):      return ("warn",   "excessive shouting")
    return ("none", "")

async def dm_user(user: discord.User | discord.Member, content: str):
    try:
        dm = await user.create_dm()
        await dm.send(content)
    except Exception:
        pass

async def log_mod(guild: discord.Guild, content: str):
    if MOD_LOG_CHANNEL_ID == 0: return
    ch = guild.get_channel(MOD_LOG_CHANNEL_ID) or await guild.fetch_channel(MOD_LOG_CHANNEL_ID)
    await ch.send(content)

def bump_strike(guild_id: int, user_id: int, window_minutes: int = 60) -> int:
    key = (guild_id, user_id)
    now = time.time()
    entry = strikes.get(key, {"count": 0, "reset_at": now + window_minutes*60})
    if now > entry["reset_at"]:
        entry = {"count": 0, "reset_at": now + window_minutes*60}
    entry["count"] += 1
    strikes[key] = entry
    return entry["count"]

# ---------- Slash commands ----------
@tree.command(name="moderate_here", description="Toggle moderation for this channel")
async def moderate_here(inter: discord.Interaction):
    if not inter.user.guild_permissions.manage_guild:
        return await inter.response.send_message("Admins only.", ephemeral=True)
    cid = inter.channel_id
    if cid in moderated_channels:
        moderated_channels.remove(cid)
        await inter.response.send_message("✅ Disabled moderation in this channel.", ephemeral=True)
    else:
        moderated_channels.add(cid)
        await inter.response.send_message("✅ Enabled moderation in this channel.", ephemeral=True)

@tree.command(name="mod_status", description="Show which channels are moderated")
async def mod_status(inter: discord.Interaction):
    names = []
    for cid in moderated_channels:
        ch = inter.guild.get_channel(cid)
        names.append(f"<#{cid}>" if ch else str(cid))
    txt = "Moderated: " + (", ".join(names) if names else "None")
    await inter.response.send_message(txt, ephemeral=True)

# ---------- Events ----------
@bot.event
async def on_ready():
    try:
        await tree.sync()
    except Exception:
        pass
    print(f"Logged in as {bot.user} (latency {bot.latency:.3f}s)")

@bot.event
async def on_message(message: discord.Message):
    # ignore self/bots
    if message.author.bot: return
    if message.guild is None: return  # ignore DMs for moderation
    if message.channel.id not in moderated_channels: return

    level, reason = classify_message(message.content)
    if level == "none":
        return

    # escalate strikes
    count = bump_strike(message.guild.id, message.author.id)

    # Prepare WhyCard text
    why = (
        f"**User:** <@{message.author.id}>\n"
        f"**Channel:** <#{message.channel.id}>\n"
        f"**Level:** {level} (strike {count})\n"
        f"**Reason:** {reason}\n"
        f"**Excerpt:** {message.content[:180]}"
    )

    try:
        if level == "warn":
            await dm_user(message.author, f"Please keep it respectful. Reason: {reason}")
            await log_mod(message.guild, why + "\n_Action_: DM warn")
        elif level == "flag":
            # delete + log
            await message.delete()
            await dm_user(message.author, "Your message was removed for targeted harassment.")
            await log_mod(message.guild, why + "\n_Action_: Deleted + warned")
        elif level == "severe":
            await message.delete()
            # timeout 30m if possible; else fallback to kick
            member = await message.guild.fetch_member(message.author.id)
            until = datetime.utcnow() + timedelta(minutes=30)
            try:
                await member.timeout(until=until, reason="Severe harassment")
                await log_mod(message.guild, why + "\n_Action_: Deleted + 30m timeout")
            except Exception:
                try:
                    await member.kick(reason="Severe harassment")
                    await log_mod(message.guild, why + "\n_Action_: Deleted + KICKED")
                except Exception:
                    await log_mod(message.guild, why + "\n_Action_: Deleted (no timeout/kick perms)")
    except discord.Forbidden:
        await log_mod(message.guild, why + "\n_Action_: FAILED (missing permission)")
    except Exception as e:
        await log_mod(message.guild, why + f"\n_Action_: ERROR {e}")

# ---------- Run ----------
if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Set DISCORD_BOT_TOKEN in .env")
    bot.run(TOKEN)

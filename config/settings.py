"""
Configuration settings for the Discord Moderation Bot
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
MOD_LOG_CHANNEL_ID = int(os.getenv("MOD_LOG_CHANNEL_ID", "0"))

# API Keys
PERSPECTIVE_API_KEY = os.getenv("PERSPECTIVE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Moderation Settings
MOD_FLAG = "[modbot]"
STRIKE_WINDOW_MINUTES = 60
MAX_MESSAGE_LENGTH = 2000

# Toxicity Thresholds
TOXICITY_THRESHOLDS = {
    "severe": 0.8,    # Immediate timeout/kick
    "moderate": 0.6,  # Delete + warn
    "mild": 0.4       # Warning only
}

# Strike Escalation
STRIKE_ESCALATION = {
    1: {"action": "warn", "duration": 0},
    2: {"action": "timeout", "duration": 15},  # 15 minutes
    3: {"action": "timeout", "duration": 60},  # 1 hour
    4: {"action": "timeout", "duration": 240}, # 4 hours
    5: {"action": "kick", "duration": 0}
}

# Punishment Durations (minutes)
PUNISHMENT_DURATIONS = {
    "warn": 0,
    "mild_timeout": 15,
    "moderate_timeout": 60,
    "severe_timeout": 240,
    "kick": 0
}

# Fallback Patterns (when APIs fail)
FALLBACK_PATTERNS = {
    "severe": [
        r"\b(kys|kill yourself|neck yourself)\b",
        r"\b(n[i1]gg[ae]r|f[a4]gg[o0]t)\b"
    ],
    "moderate": [
        r"\b(stupid|idiot|moron)\b(?=.*@)",
        r"\bstfu\b",
        r"\b(trash|garbage|worthless)\b(?=.*you|.*@)"
    ]
}
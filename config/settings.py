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

#Databae URL
DATABASE_URL = os.getenv("DATABASE_URL")

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

# Add these to your existing config/settings.py file

# Community Immunity System Settings
IMMUNITY_THRESHOLDS = {
    "trusted": 100,    # Can bypass warnings (toxicity 0.4-0.6)
    "veteran": 500,    # Can bypass minor flags (toxicity 0.6-0.7)  
    "guardian": 1000   # Can bypass all but severe violations (0.8+)
}

# Point award system
POINT_VALUES = {
    "clean_message": 1,      # Per message with toxicity < 0.1
    "helpful_reaction": 3,   # Per helpful reaction given (future feature)
    "quality_message": 5,    # Long message (>50 chars) with 0.0 toxicity
    "weekly_bonus": 50,      # 7 days without violations
    "strike_penalty": -10    # Per strike received
}

# Immunity bypass rules
IMMUNITY_RULES = {
    "severe_bypass_threshold": 0.85,  # Guardian can bypass severe < this score
    "rule_violations_stricter": True,  # Rule-based violations harder to bypass
    "max_strikes_for_immunity": 3,    # Lose immunity if strikes >= this
    "immunity_reset_on_severe": True  # Severe violation reduces points
}

# Discord role rewards (optional)
IMMUNITY_ROLES = {
    "trusted": "Trusted Member",     # Role name to assign
    "veteran": "Veteran Guardian", 
    "guardian": "Community Guardian"
}
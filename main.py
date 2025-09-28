#!/usr/bin/env python3
"""
Discord Moderation Bot - Main Entry Point
"""

import asyncio
from bot.client import create_bot
from config.settings import TOKEN

def main():
    """Main entry point for the Discord bot"""
    if not TOKEN:
        raise SystemExit("❌ Set DISCORD_BOT_TOKEN in .env file")
    
    print("🚀 Starting Discord Moderation Bot...")
    bot = create_bot()
    bot.run(TOKEN)

if __name__ == "__main__":
    main()

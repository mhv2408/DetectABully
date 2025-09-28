"""
Discord bot client setup and event handlers
"""

import discord
from discord import app_commands
from typing import Set

from config.settings import MOD_FLAG
from moderation.classifier import MessageClassifier
from moderation.actions import ModerationActions
from utils.strikes import StrikeManager
from utils.logging import ModLogger
from bot.commands import setup_commands

class ModerationBot:
    """Main Discord bot class"""
    
    def __init__(self):
        # Discord setup
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.messages = True
        
        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)
        
        # Components
        self.classifier = MessageClassifier()
        self.actions = ModerationActions()
        self.strikes = StrikeManager()
        self.logger = ModLogger()
        
        # State
        self.moderated_channels: Set[int] = set()
        
        # Setup events
        self._setup_events()
        
        # Setup commands
        setup_commands(self.tree, self)
    
    def _setup_events(self):
        """Setup Discord event handlers"""
        
        @self.client.event
        async def on_ready():
            await self._on_ready()
        
        @self.client.event
        async def on_message(message):
            await self._on_message(message)
        
        @self.client.event
        async def on_command_error(ctx, error):
            print(f"Command error: {error}")
        
        @self.tree.error
        async def on_app_command_error(inter: discord.Interaction, 
                                     error: app_commands.AppCommandError):
            if not inter.response.is_done():
                await inter.response.send_message(
                    f"❌ An error occurred: {error}", 
                    ephemeral=True
                )
    
    async def _on_ready(self):
        """Handle bot ready event"""
        # Scan all channels for moderation flag
        self.moderated_channels.clear()
        for guild in self.client.guilds:
            for channel in guild.text_channels:
                if self._topic_has_flag(channel.topic):
                    self.moderated_channels.add(channel.id)
        
        # Sync slash commands
        try:
            synced = await self.tree.sync()
            print(f"✅ Synced {len(synced)} commands")
        except Exception as e:
            print(f"❌ Failed to sync commands: {e}")
        
        print(f"🤖 {self.client.user} is ready!")
        print(f"📊 Monitoring {len(self.moderated_channels)} channels across {len(self.client.guilds)} guilds")
        print(f"🔍 Channels: {sorted(self.moderated_channels)}")
    
    async def _on_message(self, message: discord.Message):
        """Handle incoming messages for moderation"""
        # Skip bots and DMs
        if message.author.bot or message.guild is None:
            return
        
        # Only moderate flagged channels
        if message.channel.id not in self.moderated_channels:
            return
        
        # Classify message
        level, reason, analysis = await self.classifier.classify_message(
            message.content, message.author.id
        )
        
        if level == "none":
            return
        
        # Add strike
        strike_data = self.strikes.add_strike(
            message.guild.id, message.author.id, reason, level
        )
        
        # Take moderation action
        action_result = await self.actions.handle_violation(
            message, level, reason, strike_data["count"]
        )
        
        # Log the incident
        await self.logger.log_moderation_action(
            message.guild, message.author, message.channel,
            level, reason, strike_data["count"], action_result, analysis
        )
    
    def _topic_has_flag(self, topic: str | None) -> bool:
        """Check if channel topic contains moderation flag"""
        return bool(topic) and MOD_FLAG.lower() in topic.lower()
    
    def add_moderated_channel(self, channel_id: int):
        """Add channel to moderation list"""
        self.moderated_channels.add(channel_id)
    
    def remove_moderated_channel(self, channel_id: int):
        """Remove channel from moderation list"""
        self.moderated_channels.discard(channel_id)
    
    def is_channel_moderated(self, channel_id: int) -> bool:
        """Check if channel is being moderated"""
        return channel_id in self.moderated_channels
    
    def run(self, token: str):
        """Start the bot"""
        self.client.run(token)

def create_bot() -> ModerationBot:
    """Factory function to create and configure the bot"""
    return ModerationBot()
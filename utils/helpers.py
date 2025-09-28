"""
General utility functions for the Discord moderation bot
"""

import re
import time
import asyncio
from typing import List, Dict, Optional, Union, Tuple
from datetime import datetime, timezone, timedelta
import discord

def format_timestamp(timestamp: float, style: str = "R") -> str:
    """
    Format a Unix timestamp for Discord
    
    Args:
        timestamp: Unix timestamp
        style: Discord timestamp style (R=relative, F=full, etc.)
    
    Returns:
        Discord formatted timestamp string
    """
    return f"<t:{int(timestamp)}:{style}>"

def format_duration(seconds: int) -> str:
    """
    Format seconds into human-readable duration
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string (e.g., "2h 30m", "45s")
    """
    if seconds < 60:
        return f"{seconds}s"
    
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    
    hours = minutes // 60
    remaining_minutes = minutes % 60
    
    if hours < 24:
        if remaining_minutes > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{hours}h"
    
    days = hours // 24
    remaining_hours = hours % 24
    
    if remaining_hours > 0:
        return f"{days}d {remaining_hours}h"
    return f"{days}d"

def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to specified length with suffix
    
    Args:
        text: Text to truncate
        max_length: Maximum length before truncation
        suffix: Suffix to add when truncated
        
    Returns:
        Truncated text with suffix if needed
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix

def clean_text(text: str) -> str:
    """
    Clean text for analysis (remove extra whitespace, normalize)
    
    Args:
        text: Text to clean
        
    Returns:
        Cleaned text
    """
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Remove zero-width characters that might be used to evade detection
    text = re.sub(r'[\u200b-\u200d\ufeff]', '', text)
    
    return text

def extract_user_ids(text: str) -> List[int]:
    """
    Extract user IDs from Discord mentions in text
    
    Args:
        text: Text containing Discord mentions
        
    Returns:
        List of user IDs found in mentions
    """
    pattern = r'<@!?(\d+)>'
    matches = re.findall(pattern, text)
    return [int(match) for match in matches]

def extract_channel_ids(text: str) -> List[int]:
    """
    Extract channel IDs from Discord channel mentions in text
    
    Args:
        text: Text containing Discord channel mentions
        
    Returns:
        List of channel IDs found in mentions
    """
    pattern = r'<#(\d+)>'
    matches = re.findall(pattern, text)
    return [int(match) for match in matches]

def is_url(text: str) -> bool:
    """
    Check if text contains URLs
    
    Args:
        text: Text to check
        
    Returns:
        True if text contains URLs
    """
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return bool(re.search(url_pattern, text))

def get_urls(text: str) -> List[str]:
    """
    Extract URLs from text
    
    Args:
        text: Text to extract URLs from
        
    Returns:
        List of URLs found in text
    """
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(url_pattern, text)

def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculate simple similarity between two texts (Jaccard similarity)
    
    Args:
        text1: First text
        text2: Second text
        
    Returns:
        Similarity score between 0 and 1
    """
    # Convert to sets of words
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    if not words1 and not words2:
        return 1.0
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    
    return len(intersection) / len(union) if union else 0.0

def rate_limit_check(last_action_time: float, cooldown_seconds: int = 5) -> Tuple[bool, float]:
    """
    Check if action is rate limited
    
    Args:
        last_action_time: Timestamp of last action
        cooldown_seconds: Cooldown period in seconds
        
    Returns:
        Tuple of (can_proceed, time_remaining)
    """
    now = time.time()
    time_passed = now - last_action_time
    
    if time_passed >= cooldown_seconds:
        return True, 0.0
    
    return False, cooldown_seconds - time_passed

async def safe_send_message(channel: discord.TextChannel, content: str = None, 
                          embed: discord.Embed = None, **kwargs) -> Optional[discord.Message]:
    """
    Safely send a message with error handling
    
    Args:
        channel: Discord channel to send to
        content: Message content
        embed: Discord embed
        **kwargs: Additional arguments for send()
        
    Returns:
        Sent message or None if failed
    """
    try:
        return await channel.send(content=content, embed=embed, **kwargs)
    except discord.Forbidden:
        print(f"No permission to send message in {channel.name}")
        return None
    except discord.HTTPException as e:
        print(f"HTTP error sending message: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error sending message: {e}")
        return None

async def safe_delete_message(message: discord.Message, delay: float = 0) -> bool:
    """
    Safely delete a message with optional delay
    
    Args:
        message: Discord message to delete
        delay: Delay before deletion in seconds
        
    Returns:
        True if deletion was successful
    """
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        await message.delete()
        return True
    except discord.NotFound:
        return True  # Message already deleted
    except discord.Forbidden:
        print("No permission to delete message")
        return False
    except Exception as e:
        print(f"Error deleting message: {e}")
        return False

def create_progress_bar(current: int, total: int, length: int = 20, 
                       fill: str = "█", empty: str = "░") -> str:
    """
    Create a text progress bar
    
    Args:
        current: Current progress value
        total: Total/maximum value
        length: Length of progress bar in characters
        fill: Character for filled portion
        empty: Character for empty portion
        
    Returns:
        Progress bar string
    """
    if total <= 0:
        return empty * length
    
    filled_length = int(length * current / total)
    filled_length = max(0, min(length, filled_length))
    
    bar = fill * filled_length + empty * (length - filled_length)
    percentage = round(100 * current / total, 1)
    
    return f"{bar} {percentage}%"

def parse_time_string(time_str: str) -> Optional[int]:
    """
    Parse time string like "1h", "30m", "2d" into seconds
    
    Args:
        time_str: Time string to parse
        
    Returns:
        Time in seconds or None if invalid
    """
    time_str = time_str.lower().strip()
    
    # Match pattern like "1h", "30m", "2d", "45s"
    match = re.match(r'^(\d+)([smhd])$', time_str)
    if not match:
        return None
    
    amount, unit = match.groups()
    amount = int(amount)
    
    multipliers = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400
    }
    
    return amount * multipliers.get(unit, 1)

def get_member_status_emoji(member: discord.Member) -> str:
    """
    Get emoji representing member's status
    
    Args:
        member: Discord member
        
    Returns:
        Status emoji string
    """
    status_map = {
        discord.Status.online: "🟢",
        discord.Status.idle: "🟡",
        discord.Status.dnd: "🔴",
        discord.Status.offline: "⚫"
    }
    return status_map.get(member.status, "⚫")

def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """
    Split a list into chunks of specified size
    
    Args:
        lst: List to chunk
        chunk_size: Maximum size of each chunk
        
    Returns:
        List of chunked lists
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

def format_user_info(user: Union[discord.User, discord.Member]) -> str:
    """
    Format user information for display
    
    Args:
        user: Discord user or member
        
    Returns:
        Formatted user info string
    """
    info = f"{user.display_name} (`{user.id}`)"
    
    if isinstance(user, discord.Member):
        if user.nick:
            info += f"\n**Nickname:** {user.nick}"
        
        if user.joined_at:
            joined = format_timestamp(user.joined_at.timestamp(), "F")
            info += f"\n**Joined:** {joined}"
        
        status_emoji = get_member_status_emoji(user)
        info += f"\n**Status:** {status_emoji} {user.status}"
    
    created = format_timestamp(user.created_at.timestamp(), "F")
    info += f"\n**Created:** {created}"
    
    return info

class RateLimiter:
    """Simple rate limiter for API calls or actions"""
    
    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls = []
    
    def can_proceed(self) -> bool:
        """Check if action can proceed without hitting rate limit"""
        now = time.time()
        
        # Remove old calls outside the window
        self.calls = [call_time for call_time in self.calls 
                     if now - call_time < self.window_seconds]
        
        return len(self.calls) < self.max_calls
    
    def record_call(self):
        """Record that a call was made"""
        self.calls.append(time.time())
    
    def time_until_reset(self) -> float:
        """Get time in seconds until rate limit resets"""
        if not self.calls:
            return 0.0
        
        oldest_call = min(self.calls)
        reset_time = oldest_call + self.window_seconds
        
        return max(0.0, reset_time - time.time())
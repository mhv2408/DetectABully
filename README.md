# 🛡️ Detect A Bully - Discord Moderation Bot

Advanced Discord moderation bot with **AI toxicity detection** and **Community Immunity System** that rewards positive behavior.

## Video Pitch (URL) - https://youtu.be/_yVLAeilMeg

## ✨ Key Features

- **Dual AI Detection**: Google Perspective API + OpenAI for toxicity analysis
- **Community Immunity**: Good users become immune to false positives
- **Progressive Punishment**: Escalating consequences (warn → timeout → kick)
- **Rich Logging**: Professional Discord embeds with AI analysis
- **Database Persistence**: PostgreSQL for cross-session data

## 🚀 Quick Setup

### 1. Prerequisites
- Python 3.8+
- Discord Bot Token
- PostgreSQL Database (recommend [Neon](https://neon.tech/))
- Google Perspective API Key
- OpenAI API Key (optional)

### 2. Installation
```bash
git clone <repo-url>
cd DetectABully
pip install -r requirements.txt
cp .env.example .env
```

### 3. Environment Configuration
```env
DISCORD_BOT_TOKEN=your_bot_token
DATABASE_URL=postgresql://user:pass@host:5432/db
MOD_LOG_CHANNEL_ID=your_log_channel_id
PERSPECTIVE_API_KEY=your_perspective_key
OPENAI_API_KEY=your_openai_key
```

### 4. Database Setup (Table Schema)
```sql
-- Whitelist table
CREATE TABLE whitelist (
  guild_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  reason TEXT,
  added_by TEXT,
  created_at BIGINT DEFAULT (EXTRACT(EPOCH FROM NOW())::BIGINT),
  expires_at BIGINT,
  PRIMARY KEY (guild_id, user_id)
);

-- Strikes table with immunity system
CREATE TABLE strikes (
  guild_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  count INTEGER DEFAULT 0,
  reset_at BIGINT NOT NULL,
  updated_at BIGINT DEFAULT (EXTRACT(EPOCH FROM NOW())::BIGINT),
  positive_points INTEGER DEFAULT 0,
  immunity_level TEXT DEFAULT 'none',
  last_positive_update BIGINT DEFAULT 0,
  PRIMARY KEY (guild_id, user_id)
);
```

### 5. Discord Bot Permissions
- Manage Messages (delete violations)
- Moderate Members (timeout users)
- Kick Members (remove repeat offenders)
- Manage Channels (edit topics)
- Send Messages & Use Slash Commands

### 6. Run
```bash
python main.py
```

## 🎮 Usage

### Basic Setup
1. **Enable moderation**: `/moderate_here` (adds `[modbot]` to channel topic)
2. **Check status**: `/mod_status`
3. **Configure logging**: Set `MOD_LOG_CHANNEL_ID` in environment

### Core Commands
| Command | Description | Permission |
|---------|-------------|------------|
| `/moderate_here` | Toggle channel moderation | Admin |
| `/mod_status` | Show statistics | Anyone |
| `/whitelist add @user` | Exempt user from moderation | Admin |
| `/user_strikes @user` | Check violation history | Moderator |
| `/clear_strikes @user` | Reset user strikes | Admin |

### Community Immunity System
| Command | Description | Permission |
|---------|-------------|------------|
| `/user_immunity @user` | Check immunity status & points | Moderator |
| `/immunity_leaderboard` | Top community members | Anyone |
| `/award_points @user 50` | Reward good behavior | Admin |
| `/weekly_bonus` | Bulk reward system | Admin |

## 🤖 How It Works

### Detection System
1. **AI Analysis**: Messages analyzed by Perspective API + OpenAI
2. **Severity Levels**:
   - **Severe (≥0.8)**: Immediate timeout/kick
   - **Moderate (≥0.6)**: Delete + warning
   - **Mild (≥0.4)**: Warning only

3. **Rule-Based Backup**: Spam, harassment, suspicious links

### Immunity System
**Earn Points Through:**
- +1 per clean message (toxicity < 0.1)
- +5 for quality messages (>50 chars, 0.0 toxicity)
- +50 weekly bonus for good behavior
- -10 penalty per strike

**Immunity Levels:**
- **Trusted (100+ points)**: Bypass warnings
- **Veteran (500+ points)**: Bypass minor flags
- **Guardian (1000+ points)**: Bypass all but severe

### Punishment Escalation
1. **Strike 1**: Warning
2. **Strike 2**: 15min timeout
3. **Strike 3**: 1hr timeout
4. **Strike 4**: 4hr timeout
5. **Strike 5**: Server kick

## 🔧 Configuration

### Toxicity Thresholds
```python
TOXICITY_THRESHOLDS = {
    "severe": 0.8,    # Immediate action
    "moderate": 0.6,  # Delete + warn
    "mild": 0.4       # Warning only
}
```

### Server Policies
- **Strike Window**: 60 minutes (configurable)
- **Point Decay**: None (permanent reputation)
- **Immunity Bypass**: Good users protected from AI false positives
- **Admin Override**: Manual point awards and strike clearing

## 🛡️ API Integration

### Google Perspective API
- **Primary toxicity detection**
- **Categories**: TOXICITY, SEVERE_TOXICITY, IDENTITY_ATTACK, INSULT, PROFANITY, THREAT
- **Free tier available**
- **Setup**: Enable in Google Cloud Console

### OpenAI Moderation API
- **Secondary validation**
- **Categories**: hate, harassment, violence, self-harm, sexual
- **Rate limited**: 3 requests/minute (free)
- **Setup**: Get API key from OpenAI Platform

### Fallback System
- **Pattern matching** when APIs unavailable
- **Regex-based detection** for basic violations
- **Ensures 24/7 operation**

## 📊 Database Schema

### Key Tables
- **whitelist**: Permanently exempt users
- **strikes**: Violation tracking + positive points
- **Indexes**: Optimized for immunity queries

### Data Retention
- **Strikes**: Reset after window expires
- **Positive Points**: Permanent (builds reputation)
- **Cleanup**: `/cleanup_strikes` removes expired records

## ❓ Troubleshooting

### Common Issues
- **Bot not working**: Check `[modbot]` in channel topic
- **API errors**: Verify keys in `.env`
- **Permissions**: Ensure bot role above target users
- **Database**: Verify `DATABASE_URL` connection

### Debug Commands
- `/bot_info` - System diagnostics
- `/mod_status` - Current configuration
- `/user_immunity @user` - Check immunity status

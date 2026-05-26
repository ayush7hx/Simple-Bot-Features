# Simple Bot Features

A clean Discord bot with three essential server management features extracted from Dark Infinite.

## Features

### 🎉 Welcome (`greet`)
Sends a customizable welcome message when a new member joins.
- `!greet setup` — Interactive setup (choose simple text or rich embed)
- `!greet channel` — Set the welcome channel
- `!greet test` — Preview the welcome message
- `!greet config` — View current configuration
- `!greet reset` — Remove the welcome configuration

Supports placeholders: `{user}`, `{user_name}`, `{user_id}`, `{server_name}`, `{server_membercount}`, and more.

### 🏷️ AutoNick (`autonick`)
Automatically adds a prefix to new members' nicknames when they join.
- `!autonick set <prefix>` — Enable and set the prefix (e.g. `[Member]`)
- `!autonick disable` — Disable autonick
- `!autonick show` — View current status and prefix

### 📋 Embed Builder (`embed`)
Interactive builder to create and send custom embed messages.
- `!embed` — Launch the embed builder
  - Edit title, description, color, thumbnail, image, footer, author, fields
  - Send the finished embed to any channel

## Setup

1. Clone this repo
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file:
   ```
   TOKEN=your_discord_bot_token_here
   ```
4. Run the bot:
   ```
   python bot.py
   ```

## Permissions Required
- **Welcome**: No special permissions needed (bot needs Send Messages in welcome channel)
- **AutoNick**: Bot needs Manage Nicknames, user needs Manage Nicknames
- **Embed Builder**: User needs Manage Messages

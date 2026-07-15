# EDH Tournament Manager

A Python web application for managing Swiss-format tournaments for competitive Magic: The Gathering EDH (Commander) with 4-player pods.

## Features

- **Swiss Pairing System**: Intelligent pairing algorithm for 4-player pods
- **Automatic Conflict Avoidance**: Prevents players from facing each other multiple times
- **Score Tracking**: Configurable scoring system (default: 1st=3pts, 2nd=1pt, 3rd/4th=0pts)
- **Tiebreaker Calculations**: OMW%, GW%, and OGW% for accurate standings
- **Export Functionality**: Export pairings and standings to CSV and text formats
- **Edge Case Handling**: Supports odd player counts, player drops, and bye management

## Tech Stack

- **Backend**: Flask, SQLAlchemy
- **Database**: SQLite (development) / PostgreSQL (production)
- **Frontend**: Jinja2 templates + Alpine.js
- **Libraries**: pandas, Flask-WTF, Flask-Migrate

## Installation

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. Initialize the database:
   ```bash
   flask db init
   flask db migrate -m "Initial migration"
   flask db upgrade
   ```

6. Run the application:
   ```bash
   python run.py
   ```

## Usage

1. **Create Tournament**: Set up a new tournament with name and date
2. **Register Players**: Add players to the tournament
3. **Generate Pairings**: Create Swiss pairings for each round
4. **Enter Results**: Record placement for each pod (1st, 2nd, 3rd, 4th)
5. **View Standings**: See current standings with tiebreakers
6. **Export Data**: Download pairings and standings as CSV

## Discord Integration

Leagues can be linked to a Discord channel for automatic pairing announcements and player self-service signups.

**Slash commands** (in the linked channel):
- `/signup [name]` — join the league roster (defaults to your Discord name)
- `/checkin` — check in for the current week's tournament (auto-signs you up if needed)
- `/checkout` — withdraw from the current week
- `/whosplaying` — list this week's check-ins
- `/link league_id` — bind the channel to a league (requires Manage Server)

When a round is generated for a league tournament, pairings are posted to the linked channel automatically, with @mentions for players who signed up via Discord.

**Setup:**
1. Create an application at https://discord.com/developers/applications, add a bot, and invite it to your server with the `bot` + `applications.commands` scopes and Send Messages permission.
2. Set environment variables on the server: `DISCORD_APP_ID`, `DISCORD_PUBLIC_KEY`, `DISCORD_BOT_TOKEN`.
3. Set the application's **Interactions Endpoint URL** to `https://<your-host>/discord/interactions` (the app must be deployed with `DISCORD_PUBLIC_KEY` set first, or Discord's verification ping will fail).
4. Register the slash commands once: `flask discord register-commands`
5. Link a channel either way:
   - In Discord: run `/link league_id` in your league's channel, or
   - In Tabernacle: on the league dashboard, use the **Discord** card to invite the bot, paste a channel ID, and send a test message.

Check-ins go to the latest week whose tournament is in `registration` status, so create the week's tournament before players check in.

## Swiss Pairing Algorithm

The pairing algorithm:
1. Groups players by point totals
2. Within each group, forms pods of 4 players
3. Avoids repeat pairings by tracking pairing history
4. Handles odd player counts by creating 3-player pods or merging into existing pods
5. Applies tiebreakers (OMW%, GW%, OGW%) for ranking

## Testing

Run the test suite:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=app tests/
```

## License

MIT License

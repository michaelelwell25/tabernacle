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

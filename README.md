# Lesgoski

Flight deal scanner and notification system. Automatically finds cheap Ryanair round-trip flights matching your travel preferences and sends push notifications when deals appear.

## Features

- **Multi-profile support** — define different search strategies (weekend getaways, long weekends, etc.)
- **Flexible strategy editor** — pick departure/return days and time windows with a visual UI
- **Automatic scanning** — background scheduler polls the Ryanair API on a configurable interval
- **Smart deduplication** — shared flight pool across profiles, scan cooldowns to avoid redundant API calls
- **Deal matching** — reconstructs round trips from one-way flights, filters by price, duration, and schedule
- **Push notifications** — instant alerts via [ntfy.sh](https://ntfy.sh) for destinations you care about
- **Daily digest** — morning summary of the best deals across all profiles
- **Web dashboard** — FastAPI-powered UI with country filters, booking links, and profile management

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Installation

```bash
git clone https://github.com/<your-username>/lesgoski.git
cd lesgoski

# Using uv (recommended)
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
uv pip install -e .

# Or using pip
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Configuration

Copy the example env file and edit it:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./flights.db` | Database connection string |
| `NTFY_TOPIC` | *(empty)* | Your ntfy.sh topic for push notifications |
| `SCAN_COOLDOWN_MINUTES` | `30` | Min time between scanning the same origin |
| `LOOKUP_HORIZON_DAYS` | `120` | How far ahead to search for flights |
| `HOUR_TOLERANCE` | `1` | Hours of tolerance on time window matching |
| `UPDATE_INTERVAL_MINUTES` | `180` | How often profiles are refreshed |
| `FLIGHT_STALENESS_HOURS` | `24` | Prune flights older than this |

### Running

**Web dashboard:**

```bash
lesgoski-web
# or: uvicorn lesgoski.webapp.app:app --reload
```

Open http://localhost:8000 to create a profile and view deals.

**Background scheduler:**

```bash
lesgoski-scheduler
```

Runs in a loop: scans flights, matches deals, sends notifications, and prunes stale data.

## Project Structure

```
src/lesgoski/
├── config.py              # Centralized settings (env vars)
├── core/
│   └── schemas.py         # Pydantic models (FlightSchema, StrategyConfig)
├── database/
│   ├── engine.py          # SQLAlchemy engine, session factory
│   └── models.py          # ORM models (Flight, SearchProfile, Deal, ScanLog)
├── services/
│   ├── scanner.py         # Queries Ryanair API for cheap flights
│   ├── matcher.py         # Reconstructs round trips from one-way flights
│   ├── notifier.py        # Push notifications via ntfy.sh
│   └── orchestrator.py    # Scanner → Matcher → Notifier pipeline
├── scheduler/
│   └── runner.py          # Background job runner
└── webapp/
    ├── app.py             # FastAPI application and routes
    ├── utils.py           # Country codes, booking URL builders
    ├── static/            # CSS, JS
    ├── templates/         # Jinja2 HTML templates
    └── data/              # Airport CSV, country codes JSON
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Scanner    │────>│   Matcher   │────>│  Notifier   │
│ (Ryanair API)│     │(Round trips)│     │  (ntfy.sh)  │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                    │
       └───────────────────┴────────────────────┘
                           │
                    ┌──────┴──────┐
                    │  SQLite DB  │
                    │  (flights,  │
                    │  profiles,  │
                    │   deals)    │
                    └─────────────┘
```

The **Orchestrator** coordinates the pipeline for each profile. The **Scheduler** runs this periodically. The **Webapp** provides a UI to manage profiles and browse deals.

## License

MIT

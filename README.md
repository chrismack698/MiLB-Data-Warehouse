# MiLB Stats Warehouse

Current-season MiLB game-log warehouse for analytics, Streamlit apps, and data
science workflows.

The project extracts completed affiliated Minor League games from the MLB Stats
API, normalizes batter and pitcher game logs, adds pitcher whiffs from
pitch-by-pitch events, writes local Parquet snapshots, and can load the results
into MotherDuck.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run One Date

```powershell
python -m milb_warehouse.cli --date 2026-04-30
```

## Run a Date Range

```powershell
python -m milb_warehouse.cli --start-date 2026-03-27 --end-date 2026-04-30
```

Outputs:

```text
data/parquet/batter_game_logs/game_date=YYYY-MM-DD/batter_game_logs.parquet
data/parquet/pitcher_game_logs/game_date=YYYY-MM-DD/pitcher_game_logs.parquet
data/parquet/pitch_events/game_date=YYYY-MM-DD/pitch_events.parquet
data/parquet/batted_ball_events/game_date=YYYY-MM-DD/batted_ball_events.parquet
data/parquet/players/game_date=YYYY-MM-DD/players.parquet
```

## Load MotherDuck

Set your token first:

```powershell
$env:motherduck_token = "..."
```

Then run:

```powershell
python -m milb_warehouse.cli --date 2026-04-30 --motherduck-db milb_stats
```

For a season backfill, run:

```powershell
python -m milb_warehouse.cli --start-date 2026-03-27 --end-date 2026-04-30 --motherduck-db milb_stats
```

To populate or refresh player metadata from rows already loaded in MotherDuck,
without reloading historical games:

```powershell
python -m milb_warehouse.cli --refresh-players-only --motherduck-db milb_stats
```

The loader deletes and reloads the requested date, which makes daily runs
idempotent. Date ranges run serially and reuse one MotherDuck connection.

MotherDuck tables:

- `players`
- `batter_game_logs`
- `pitcher_game_logs`
- `pitch_events`
- `batted_ball_events`

Each fact table has a database-generated surrogate key:

- `batter_game_logs.batter_game_log_id`
- `pitcher_game_logs.pitcher_game_log_id`
- `pitch_events.pitch_event_id`
- `batted_ball_events.batted_ball_event_id`

Each fact table also has a `season` column so historical backfills can coexist
with future seasons.

The `players` table stores player metadata from MLB Stats API game feeds,
including `birth_date`, handedness, position, draft year, and MLB debut date.
It is not limited to MiLB players; it can store any player returned by loaded
game feeds, including MLB players if MLB games are loaded with `--sport-ids 1`.
Enriched game-log views calculate `player_age` from `players.birth_date` as of
each `game_date`.

Use the event-level tables for Statcast-style aggregates so you do not average
game-level averages. For example:

```sql
SELECT
    batter_id,
    batter_name,
    COUNT(*) AS bbe,
    AVG(launch_speed) AS avg_ev,
    MAX(launch_speed) AS max_ev,
    AVG(launch_angle) AS avg_la
FROM batted_ball_events
GROUP BY batter_id, batter_name;
```

```sql
SELECT
    pitcher_id,
    pitcher_name,
    pitch_type,
    COUNT(*) AS pitches,
    AVG(start_speed) AS avg_velocity,
    AVG(spin_rate) AS avg_spin_rate,
    SUM(CASE WHEN is_whiff THEN 1 ELSE 0 END)::DOUBLE / COUNT(*) AS whiff_pct
FROM pitch_events
GROUP BY pitcher_id, pitcher_name, pitch_type;
```

Convenience views `batter_statcast_summary` and
`pitcher_pitch_type_summary` are also created from the event-level tables.

## Daily GitHub Actions Load

The workflow at `.github/workflows/daily-motherduck-load.yml` runs every day at
10:00 UTC and computes the load date as yesterday in `America/Chicago`.

Configure these repository settings in GitHub:

- Secret `MOTHERDUCK_TOKEN`: your MotherDuck token.
- Variable `MOTHERDUCK_DB`: the target database name. If omitted, the workflow
  uses `milb_stats`.

You can also run the workflow manually from the GitHub Actions tab and provide a
specific `game_date` such as `2026-04-30`. The load is idempotent for each date:
the existing rows for that `game_date` are deleted and reinserted.

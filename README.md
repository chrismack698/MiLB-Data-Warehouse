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

Outputs:

```text
data/parquet/batter_game_logs/game_date=YYYY-MM-DD/batter_game_logs.parquet
data/parquet/pitcher_game_logs/game_date=YYYY-MM-DD/pitcher_game_logs.parquet
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

The loader deletes and reloads the requested date, which makes daily runs
idempotent.

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

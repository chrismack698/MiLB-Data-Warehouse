from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from .api import StatsApiClient
from .constants import DEFAULT_SPORT_IDS
from .extract import extract_game_logs, frames_from_rows, is_final_game
from .storage import connect_motherduck, reload_game_log_date, write_parquet_snapshot


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_args() -> argparse.Namespace:
    default_date = (date.today() - timedelta(days=1)).isoformat()
    parser = argparse.ArgumentParser(description="Build MiLB warehouse game logs for one date.")
    parser.add_argument("--date", default=default_date, help="Game date to extract, YYYY-MM-DD.")
    parser.add_argument(
        "--sport-ids",
        default=",".join(str(sport_id) for sport_id in DEFAULT_SPORT_IDS),
        help="Comma-separated MLB Stats API sport IDs. Default: 11,12,13,14,16.",
    )
    parser.add_argument("--cache-dir", default="data/raw_debug/mlb_stats_api")
    parser.add_argument("--parquet-dir", default="data/parquet")
    parser.add_argument("--motherduck-db", default="", help="MotherDuck database name, e.g. milb_stats.")
    parser.add_argument("--delay", type=float, default=0.15)
    parser.add_argument("--request-timeout", type=float, default=15.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--limit-games", type=int, default=0)
    return parser.parse_args()


def project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def extract_for_date(
    game_date: date,
    sport_ids: tuple[int, ...],
    client: StatsApiClient,
    limit_games: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    whiff_codes = client.whiff_codes()
    batter_rows: list[dict[str, Any]] = []
    pitcher_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    seen_games: set[int] = set()

    for sport_id in sport_ids:
        try:
            games = client.schedule(sport_id, game_date)
        except Exception as exc:
            error_rows.append(
                {"scope": "schedule", "sport_id": sport_id, "game_pk": None, "error": str(exc)}
            )
            continue

        final_games = [
            game
            for game in games
            if game.get("gamePk") and game["gamePk"] not in seen_games and is_final_game(game)
        ]
        print(f"sportId {sport_id}: {len(final_games)} completed games", flush=True)

        for game in final_games:
            game_pk = int(game["gamePk"])
            seen_games.add(game_pk)
            away = game.get("teams", {}).get("away", {}).get("team", {}).get("name", "Away")
            home = game.get("teams", {}).get("home", {}).get("team", {}).get("name", "Home")
            print(f"  gamePk {game_pk}: {away} at {home}", flush=True)

            try:
                live_data = client.live_game(game_pk)
                batters, pitchers = extract_game_logs(game, live_data, sport_id, whiff_codes)
            except Exception as exc:
                error_rows.append(
                    {"scope": "game", "sport_id": sport_id, "game_pk": game_pk, "error": str(exc)}
                )
                print(f"    skipped: {exc}", flush=True)
                continue

            batter_rows.extend(batters)
            pitcher_rows.extend(pitchers)

            if limit_games and len(seen_games) >= limit_games:
                print(f"Reached --limit-games {limit_games}", flush=True)
                return (*frames_from_rows(batter_rows, pitcher_rows), pd.DataFrame(error_rows))

    return (*frames_from_rows(batter_rows, pitcher_rows), pd.DataFrame(error_rows))


def main() -> None:
    args = parse_args()
    game_date = parse_date(args.date)
    sport_ids = tuple(int(value.strip()) for value in args.sport_ids.split(",") if value.strip())
    cache_dir = project_path(args.cache_dir)
    parquet_dir = project_path(args.parquet_dir)

    client = StatsApiClient(
        cache_dir=cache_dir,
        delay=args.delay,
        force_refresh=args.force_refresh,
        request_timeout=args.request_timeout,
        retries=args.retries,
    )

    print(f"Extracting MiLB game logs for {game_date.isoformat()}", flush=True)
    batters, pitchers, errors = extract_for_date(game_date, sport_ids, client, args.limit_games)

    batter_path = write_parquet_snapshot(batters, parquet_dir, "batter_game_logs", game_date)
    pitcher_path = write_parquet_snapshot(pitchers, parquet_dir, "pitcher_game_logs", game_date)
    print(f"Wrote {len(batters):,} batter rows to {batter_path}", flush=True)
    print(f"Wrote {len(pitchers):,} pitcher rows to {pitcher_path}", flush=True)

    if not errors.empty:
        error_dir = PROJECT_ROOT / "data" / "raw_debug"
        error_dir.mkdir(parents=True, exist_ok=True)
        error_path = error_dir / f"errors_{game_date.isoformat()}.csv"
        errors.to_csv(error_path, index=False)
        print(f"Wrote {len(errors):,} errors to {error_path}", flush=True)

    if args.motherduck_db:
        con = connect_motherduck(args.motherduck_db)
        try:
            reload_game_log_date(con, batters, pitchers, game_date)
        finally:
            con.close()
        print(f"Reloaded {game_date.isoformat()} into MotherDuck database {args.motherduck_db}", flush=True)


if __name__ == "__main__":
    main()

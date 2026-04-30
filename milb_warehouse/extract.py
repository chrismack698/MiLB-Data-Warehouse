from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Any

import pandas as pd

from .constants import BATTER_COLUMNS, PITCHER_COLUMNS, SPORT_LEVELS


def is_final_game(game: dict[str, Any]) -> bool:
    status = game.get("status", {})
    return status.get("abstractGameState") == "Final" or status.get("detailedState") in {
        "Final",
        "Completed Early",
    }


def display_level(sport_id: int, league_name: str | None) -> str:
    if sport_id != 16 or not league_name:
        return SPORT_LEVELS.get(sport_id, str(sport_id))

    normalized = league_name.lower()
    if "dominican summer" in normalized:
        return "DSL"
    if "arizona complex" in normalized:
        return "ACL"
    if "florida complex" in normalized:
        return "FCL"
    return "R"


def team_context(game: dict[str, Any], side: str, sport_id: int) -> dict[str, Any]:
    team = game["teams"][side]["team"]
    league = team.get("league", {})
    league_name = league.get("name") or SPORT_LEVELS.get(sport_id)
    return {
        "team_id": team.get("id"),
        "team_name": team.get("name") or team.get("teamName"),
        "level": display_level(sport_id, league_name),
    }


def int_stat(stats: dict[str, Any], key: str) -> int:
    value = stats.get(key, 0)
    if value in ("", None, "-.--"):
        return 0
    return int(float(value))


def parse_ip_to_outs(value: Any) -> int:
    if value in ("", None, "-.--"):
        return 0
    whole, _, frac = str(value).partition(".")
    return int(whole or 0) * 3 + int(frac or 0)


def maybe_float(value: Any) -> float | None:
    if value in ("", None, "-.--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def average(values: list[float]) -> float | None:
    return round(mean(values), 3) if values else None


def game_date_from(game: dict[str, Any]) -> str:
    return datetime.fromisoformat(game["gameDate"].replace("Z", "+00:00")).date().isoformat()


def collect_event_metrics(
    live_data: dict[str, Any], whiff_codes: set[str]
) -> tuple[dict[tuple[int, int], dict[str, Any]], dict[tuple[int, int], dict[str, Any]]]:
    batter_metrics: dict[tuple[int, int], dict[str, Any]] = defaultdict(
        lambda: {"evs": [], "las": [], "hard_hit": 0, "bbe": 0}
    )
    pitcher_metrics: dict[tuple[int, int], dict[str, Any]] = defaultdict(
        lambda: {
            "whiffs": 0,
            "velos": [],
            "tracked_pitches": 0,
            "evs_allowed": [],
            "hard_hit_allowed": 0,
            "bbe_allowed": 0,
        }
    )

    plays = live_data.get("liveData", {}).get("plays", {}).get("allPlays", [])
    game_pk = live_data.get("gamePk")
    if not game_pk:
        game_pk = live_data.get("gameData", {}).get("game", {}).get("pk")

    for play in plays:
        matchup = play.get("matchup", {})
        batter_id = matchup.get("batter", {}).get("id")
        pitcher_id = matchup.get("pitcher", {}).get("id")
        if not batter_id or not pitcher_id or not game_pk:
            continue

        batter_key = (int(game_pk), int(batter_id))
        pitcher_key = (int(game_pk), int(pitcher_id))

        for event in play.get("playEvents", []):
            if event.get("isPitch"):
                code = event.get("details", {}).get("code")
                if code in whiff_codes:
                    pitcher_metrics[pitcher_key]["whiffs"] += 1

                velocity = maybe_float(event.get("pitchData", {}).get("startSpeed"))
                if velocity is not None:
                    pitcher_metrics[pitcher_key]["velos"].append(velocity)
                    pitcher_metrics[pitcher_key]["tracked_pitches"] += 1

            hit_data = event.get("hitData", {})
            ev = maybe_float(hit_data.get("launchSpeed"))
            la = maybe_float(hit_data.get("launchAngle"))
            if ev is None and la is None:
                continue

            batter_metrics[batter_key]["bbe"] += 1
            pitcher_metrics[pitcher_key]["bbe_allowed"] += 1

            if ev is not None:
                batter_metrics[batter_key]["evs"].append(ev)
                pitcher_metrics[pitcher_key]["evs_allowed"].append(ev)
                if ev >= 95:
                    batter_metrics[batter_key]["hard_hit"] += 1
                    pitcher_metrics[pitcher_key]["hard_hit_allowed"] += 1

            if la is not None:
                batter_metrics[batter_key]["las"].append(la)

    return batter_metrics, pitcher_metrics


def extract_game_logs(
    game: dict[str, Any], live_data: dict[str, Any], sport_id: int, whiff_codes: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    game_pk = int(game["gamePk"])
    game_date = game_date_from(game)
    boxscore = live_data.get("liveData", {}).get("boxscore", {})
    teams = boxscore.get("teams", {})
    batter_metrics, pitcher_metrics = collect_event_metrics(live_data, whiff_codes)

    batter_rows: list[dict[str, Any]] = []
    pitcher_rows: list[dict[str, Any]] = []

    for side in ("away", "home"):
        context = team_context(game, side, sport_id)
        team_box = teams.get(side, {})

        for player_blob in team_box.get("players", {}).values():
            person = player_blob.get("person", {})
            player_id = person.get("id")
            if not player_id:
                continue

            common = {
                "player_id": int(player_id),
                "player_name": person.get("fullName"),
                "game_pk": game_pk,
                "game_date": game_date,
                "team_id": context["team_id"],
                "team_name": context["team_name"],
                "level": context["level"],
            }

            batting = player_blob.get("stats", {}).get("batting", {})
            if batting and int_stat(batting, "plateAppearances") > 0:
                h = int_stat(batting, "hits")
                doubles = int_stat(batting, "doubles")
                triples = int_stat(batting, "triples")
                hr = int_stat(batting, "homeRuns")
                metrics = batter_metrics.get((game_pk, int(player_id)), {})
                bbe = metrics.get("bbe", 0)
                hard_hit = metrics.get("hard_hit", 0)
                row = {
                    **common,
                    "ab": int_stat(batting, "atBats"),
                    "pa": int_stat(batting, "plateAppearances"),
                    "h": h,
                    "singles": max(h - doubles - triples - hr, 0),
                    "doubles": doubles,
                    "triples": triples,
                    "hr": hr,
                    "r": int_stat(batting, "runs"),
                    "rbi": int_stat(batting, "rbi"),
                    "bb": int_stat(batting, "baseOnBalls"),
                    "ibb": int_stat(batting, "intentionalWalks"),
                    "so": int_stat(batting, "strikeOuts"),
                    "hbp": int_stat(batting, "hitByPitch"),
                    "sf": int_stat(batting, "sacFlies"),
                    "sh": int_stat(batting, "sacBunts"),
                    "gdp": int_stat(batting, "groundIntoDoublePlay"),
                    "sb": int_stat(batting, "stolenBases"),
                    "cs": int_stat(batting, "caughtStealing"),
                    "bbe": bbe,
                    "avg_ev": average(metrics.get("evs", [])),
                    "max_ev": max(metrics.get("evs", []), default=None),
                    "hard_hit": hard_hit,
                    "hard_hit_pct": round(hard_hit / bbe, 3) if bbe else None,
                    "avg_la": average(metrics.get("las", [])),
                }
                batter_rows.append(row)

            pitching = player_blob.get("stats", {}).get("pitching", {})
            if pitching and parse_ip_to_outs(pitching.get("inningsPitched")) > 0:
                metrics = pitcher_metrics.get((game_pk, int(player_id)), {})
                bbe_allowed = metrics.get("bbe_allowed", 0)
                hard_hit_allowed = metrics.get("hard_hit_allowed", 0)
                row = {
                    **common,
                    "whiffs": metrics.get("whiffs", 0),
                    "pitches": int_stat(pitching, "pitchesThrown"),
                    "batters_faced": int_stat(pitching, "battersFaced"),
                    "w": int_stat(pitching, "wins"),
                    "l": int_stat(pitching, "losses"),
                    "cg": int_stat(pitching, "completeGames"),
                    "sho": int_stat(pitching, "shutouts"),
                    "sv": int_stat(pitching, "saves"),
                    "ip_outs": parse_ip_to_outs(pitching.get("inningsPitched")),
                    "tbf": int_stat(pitching, "battersFaced"),
                    "h": int_stat(pitching, "hits"),
                    "r": int_stat(pitching, "runs"),
                    "er": int_stat(pitching, "earnedRuns"),
                    "hr": int_stat(pitching, "homeRuns"),
                    "bb": int_stat(pitching, "baseOnBalls"),
                    "ibb": int_stat(pitching, "intentionalWalks"),
                    "hbp": int_stat(pitching, "hitByPitch"),
                    "wp": int_stat(pitching, "wildPitches"),
                    "bk": int_stat(pitching, "balks"),
                    "so": int_stat(pitching, "strikeOuts"),
                    "tracked_pitches": metrics.get("tracked_pitches", 0),
                    "avg_velocity": average(metrics.get("velos", [])),
                    "max_velocity": max(metrics.get("velos", []), default=None),
                    "bbe_allowed": bbe_allowed,
                    "avg_ev_allowed": average(metrics.get("evs_allowed", [])),
                    "hard_hit_allowed": hard_hit_allowed,
                    "hard_hit_pct_allowed": (
                        round(hard_hit_allowed / bbe_allowed, 3) if bbe_allowed else None
                    ),
                }
                pitcher_rows.append(row)

    return batter_rows, pitcher_rows


def frames_from_rows(
    batter_rows: list[dict[str, Any]], pitcher_rows: list[dict[str, Any]]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    batters = pd.DataFrame(batter_rows, columns=BATTER_COLUMNS)
    pitchers = pd.DataFrame(pitcher_rows, columns=PITCHER_COLUMNS)

    for df in (batters, pitchers):
        if not df.empty:
            df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
            df.sort_values(["game_date", "level", "team_name", "player_name"], inplace=True)
            df.reset_index(drop=True, inplace=True)

    return batters, pitchers

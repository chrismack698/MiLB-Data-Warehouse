from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Any

import pandas as pd

from .constants import (
    BATTED_BALL_COLUMNS,
    BATTER_COLUMNS,
    PITCHER_COLUMNS,
    PITCH_EVENT_COLUMNS,
    SPORT_LEVELS,
)


def is_final_game(game: dict[str, Any]) -> bool:
    status = game.get("status", {})
    detailed_state = status.get("detailedState")
    if detailed_state in {"Postponed", "Suspended", "Cancelled"}:
        return False
    return status.get("abstractGameState") == "Final" or detailed_state in {"Final", "Completed Early"}


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


def team_contexts_by_side(game: dict[str, Any], sport_id: int) -> dict[str, dict[str, Any]]:
    return {side: team_context(game, side, sport_id) for side in ("away", "home")}


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
    if game.get("officialDate"):
        return str(game["officialDate"])
    return datetime.fromisoformat(game["gameDate"].replace("Z", "+00:00")).date().isoformat()


def season_from(game: dict[str, Any]) -> int:
    if game.get("season"):
        return int(game["season"])
    return int(game_date_from(game)[:4])


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


def side_context_for_play(
    play: dict[str, Any], team_contexts: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    is_top_inning = play.get("about", {}).get("isTopInning")
    if is_top_inning:
        return team_contexts["away"], team_contexts["home"]
    return team_contexts["home"], team_contexts["away"]


def event_context(
    game: dict[str, Any],
    play: dict[str, Any],
    event: dict[str, Any],
    sport_id: int,
    whiff_codes: set[str],
    team_contexts: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    matchup = play.get("matchup", {})
    batter = matchup.get("batter", {})
    pitcher = matchup.get("pitcher", {})
    batter_id = batter.get("id")
    pitcher_id = pitcher.get("id")
    if not batter_id or not pitcher_id:
        return None

    batter_team, pitcher_team = side_context_for_play(play, team_contexts)
    about = play.get("about", {})
    details = event.get("details", {})
    pitch_type = details.get("type", {})
    count = event.get("count", {})
    pitch_data = event.get("pitchData", {})
    coordinates = pitch_data.get("coordinates", {})
    breaks = pitch_data.get("breaks", {})
    hit_data = event.get("hitData", {})
    code = details.get("code")

    return {
        "game_pk": int(game["gamePk"]),
        "game_date": game_date_from(game),
        "season": season_from(game),
        "sport_id": sport_id,
        "level": batter_team["level"],
        "inning": about.get("inning"),
        "half_inning": about.get("halfInning"),
        "at_bat_index": about.get("atBatIndex"),
        "event_index": event.get("index"),
        "play_id": event.get("playId"),
        "pitch_number": event.get("pitchNumber"),
        "batter_id": int(batter_id),
        "batter_name": batter.get("fullName"),
        "pitcher_id": int(pitcher_id),
        "pitcher_name": pitcher.get("fullName"),
        "batter_team_id": batter_team["team_id"],
        "batter_team_name": batter_team["team_name"],
        "pitcher_team_id": pitcher_team["team_id"],
        "pitcher_team_name": pitcher_team["team_name"],
        "bat_side": matchup.get("batSide", {}).get("code"),
        "pitch_hand": matchup.get("pitchHand", {}).get("code"),
        "balls": count.get("balls"),
        "strikes": count.get("strikes"),
        "outs": count.get("outs"),
        "pitch_type": pitch_type.get("code"),
        "pitch_name": pitch_type.get("description"),
        "call_code": code,
        "call_description": details.get("description"),
        "event_type": play.get("result", {}).get("eventType"),
        "result_event": play.get("result", {}).get("event"),
        "result_description": play.get("result", {}).get("description"),
        "is_in_play": details.get("isInPlay"),
        "is_strike": details.get("isStrike"),
        "is_ball": details.get("isBall"),
        "is_out": details.get("isOut"),
        "is_whiff": code in whiff_codes,
        "start_speed": maybe_float(pitch_data.get("startSpeed")),
        "end_speed": maybe_float(pitch_data.get("endSpeed")),
        "zone": pitch_data.get("zone"),
        "plate_x": maybe_float(coordinates.get("pX")),
        "plate_z": maybe_float(coordinates.get("pZ")),
        "extension": maybe_float(pitch_data.get("extension")),
        "spin_rate": maybe_float(breaks.get("spinRate")),
        "spin_direction": maybe_float(breaks.get("spinDirection")),
        "break_horizontal": maybe_float(breaks.get("breakHorizontal")),
        "break_vertical_induced": maybe_float(breaks.get("breakVerticalInduced")),
        "launch_speed": maybe_float(hit_data.get("launchSpeed")),
        "launch_angle": maybe_float(hit_data.get("launchAngle")),
        "total_distance": maybe_float(hit_data.get("totalDistance")),
        "trajectory": hit_data.get("trajectory"),
        "hardness": hit_data.get("hardness"),
        "hit_location": hit_data.get("location"),
        "coord_x": maybe_float(hit_data.get("coordinates", {}).get("coordX")),
        "coord_y": maybe_float(hit_data.get("coordinates", {}).get("coordY")),
    }


def extract_event_rows(
    game: dict[str, Any], live_data: dict[str, Any], sport_id: int, whiff_codes: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    team_contexts = team_contexts_by_side(game, sport_id)
    pitch_rows: list[dict[str, Any]] = []
    batted_ball_rows: list[dict[str, Any]] = []

    plays = live_data.get("liveData", {}).get("plays", {}).get("allPlays", [])
    for play in plays:
        for event in play.get("playEvents", []):
            if not event.get("isPitch"):
                continue

            row = event_context(game, play, event, sport_id, whiff_codes, team_contexts)
            if row is None:
                continue

            pitch_rows.append({column: row.get(column) for column in PITCH_EVENT_COLUMNS})

            if row.get("launch_speed") is not None or row.get("launch_angle") is not None:
                batted_ball_row = {column: row.get(column) for column in BATTED_BALL_COLUMNS}
                launch_speed = row.get("launch_speed")
                batted_ball_row["is_hard_hit"] = launch_speed is not None and launch_speed >= 95
                batted_ball_rows.append(batted_ball_row)

    return pitch_rows, batted_ball_rows


def extract_game_logs(
    game: dict[str, Any], live_data: dict[str, Any], sport_id: int, whiff_codes: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    game_pk = int(game["gamePk"])
    game_date = game_date_from(game)
    season = season_from(game)
    boxscore = live_data.get("liveData", {}).get("boxscore", {})
    teams = boxscore.get("teams", {})
    batter_metrics, pitcher_metrics = collect_event_metrics(live_data, whiff_codes)
    pitch_event_rows, batted_ball_rows = extract_event_rows(game, live_data, sport_id, whiff_codes)

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
                "season": season,
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

    return batter_rows, pitcher_rows, pitch_event_rows, batted_ball_rows


def frames_from_rows(
    batter_rows: list[dict[str, Any]],
    pitcher_rows: list[dict[str, Any]],
    pitch_event_rows: list[dict[str, Any]] | None = None,
    batted_ball_rows: list[dict[str, Any]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    batters = pd.DataFrame(batter_rows, columns=BATTER_COLUMNS)
    pitchers = pd.DataFrame(pitcher_rows, columns=PITCHER_COLUMNS)
    pitch_events = pd.DataFrame(pitch_event_rows or [], columns=PITCH_EVENT_COLUMNS)
    batted_balls = pd.DataFrame(batted_ball_rows or [], columns=BATTED_BALL_COLUMNS)

    for df in (batters, pitchers, pitch_events, batted_balls):
        if not df.empty:
            df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
            event_sort = ["game_date", "game_pk", "at_bat_index", "event_index"]
            log_sort = ["game_date", "level", "team_name", "player_name"]
            sort_columns = event_sort if "at_bat_index" in df else log_sort
            df.sort_values(sort_columns, inplace=True)
            df.reset_index(drop=True, inplace=True)

    return batters, pitchers, pitch_events, batted_balls

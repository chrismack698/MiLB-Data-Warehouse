from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from .constants import BATTED_BALL_COLUMNS, BATTER_COLUMNS, PITCHER_COLUMNS, PITCH_EVENT_COLUMNS

if TYPE_CHECKING:
    import duckdb


def write_parquet_snapshot(df: pd.DataFrame, root: Path, table_name: str, game_date: date) -> Path:
    output_dir = root / table_name / f"game_date={game_date.isoformat()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{table_name}.parquet"
    df.to_parquet(output_path, index=False)
    return output_path


def connect_motherduck(database: str) -> duckdb.DuckDBPyConnection:
    import duckdb

    return duckdb.connect(f"md:{database}")


def create_tables(con: "duckdb.DuckDBPyConnection") -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS batter_game_logs (
            player_id INTEGER,
            player_name VARCHAR,
            game_pk INTEGER,
            game_date DATE,
            team_id INTEGER,
            team_name VARCHAR,
            level VARCHAR,
            ab INTEGER,
            pa INTEGER,
            h INTEGER,
            singles INTEGER,
            doubles INTEGER,
            triples INTEGER,
            hr INTEGER,
            r INTEGER,
            rbi INTEGER,
            bb INTEGER,
            ibb INTEGER,
            so INTEGER,
            hbp INTEGER,
            sf INTEGER,
            sh INTEGER,
            gdp INTEGER,
            sb INTEGER,
            cs INTEGER,
            bbe INTEGER,
            avg_ev DOUBLE,
            max_ev DOUBLE,
            hard_hit INTEGER,
            hard_hit_pct DOUBLE,
            avg_la DOUBLE
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pitcher_game_logs (
            player_id INTEGER,
            player_name VARCHAR,
            game_pk INTEGER,
            game_date DATE,
            team_id INTEGER,
            team_name VARCHAR,
            level VARCHAR,
            whiffs INTEGER,
            pitches INTEGER,
            batters_faced INTEGER,
            w INTEGER,
            l INTEGER,
            cg INTEGER,
            sho INTEGER,
            sv INTEGER,
            ip_outs INTEGER,
            tbf INTEGER,
            h INTEGER,
            r INTEGER,
            er INTEGER,
            hr INTEGER,
            bb INTEGER,
            ibb INTEGER,
            hbp INTEGER,
            wp INTEGER,
            bk INTEGER,
            so INTEGER,
            tracked_pitches INTEGER,
            avg_velocity DOUBLE,
            max_velocity DOUBLE,
            bbe_allowed INTEGER,
            avg_ev_allowed DOUBLE,
            hard_hit_allowed INTEGER,
            hard_hit_pct_allowed DOUBLE
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pitch_events (
            game_pk INTEGER,
            game_date DATE,
            sport_id INTEGER,
            level VARCHAR,
            inning INTEGER,
            half_inning VARCHAR,
            at_bat_index INTEGER,
            event_index INTEGER,
            play_id VARCHAR,
            pitch_number INTEGER,
            batter_id INTEGER,
            batter_name VARCHAR,
            pitcher_id INTEGER,
            pitcher_name VARCHAR,
            batter_team_id INTEGER,
            batter_team_name VARCHAR,
            pitcher_team_id INTEGER,
            pitcher_team_name VARCHAR,
            bat_side VARCHAR,
            pitch_hand VARCHAR,
            balls INTEGER,
            strikes INTEGER,
            outs INTEGER,
            pitch_type VARCHAR,
            pitch_name VARCHAR,
            call_code VARCHAR,
            call_description VARCHAR,
            event_type VARCHAR,
            result_event VARCHAR,
            result_description VARCHAR,
            is_in_play BOOLEAN,
            is_strike BOOLEAN,
            is_ball BOOLEAN,
            is_out BOOLEAN,
            is_whiff BOOLEAN,
            start_speed DOUBLE,
            end_speed DOUBLE,
            zone INTEGER,
            plate_x DOUBLE,
            plate_z DOUBLE,
            extension DOUBLE,
            spin_rate DOUBLE,
            spin_direction DOUBLE,
            break_horizontal DOUBLE,
            break_vertical_induced DOUBLE,
            launch_speed DOUBLE,
            launch_angle DOUBLE
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS batted_ball_events (
            game_pk INTEGER,
            game_date DATE,
            sport_id INTEGER,
            level VARCHAR,
            inning INTEGER,
            half_inning VARCHAR,
            at_bat_index INTEGER,
            event_index INTEGER,
            play_id VARCHAR,
            pitch_number INTEGER,
            batter_id INTEGER,
            batter_name VARCHAR,
            pitcher_id INTEGER,
            pitcher_name VARCHAR,
            batter_team_id INTEGER,
            batter_team_name VARCHAR,
            pitcher_team_id INTEGER,
            pitcher_team_name VARCHAR,
            bat_side VARCHAR,
            pitch_hand VARCHAR,
            balls INTEGER,
            strikes INTEGER,
            outs INTEGER,
            pitch_type VARCHAR,
            pitch_name VARCHAR,
            call_code VARCHAR,
            call_description VARCHAR,
            event_type VARCHAR,
            result_event VARCHAR,
            result_description VARCHAR,
            launch_speed DOUBLE,
            launch_angle DOUBLE,
            total_distance DOUBLE,
            trajectory VARCHAR,
            hardness VARCHAR,
            hit_location VARCHAR,
            coord_x DOUBLE,
            coord_y DOUBLE,
            is_hard_hit BOOLEAN
        )
        """
    )
    create_views(con)


def create_views(con: "duckdb.DuckDBPyConnection") -> None:
    con.execute(
        """
        CREATE OR REPLACE VIEW batter_game_logs_enriched AS
        SELECT
            *,
            h::DOUBLE / NULLIF(ab, 0) AS avg,
            bb::DOUBLE / NULLIF(pa, 0) AS bb_pct,
            so::DOUBLE / NULLIF(pa, 0) AS k_pct,
            bb::DOUBLE / NULLIF(so, 0) AS bb_per_k,
            (h + bb + hbp)::DOUBLE / NULLIF(ab + bb + hbp + sf, 0) AS obp,
            (singles + 2*doubles + 3*triples + 4*hr)::DOUBLE / NULLIF(ab, 0) AS slg,
            (
                (h + bb + hbp)::DOUBLE / NULLIF(ab + bb + hbp + sf, 0)
                + (singles + 2*doubles + 3*triples + 4*hr)::DOUBLE / NULLIF(ab, 0)
            ) AS ops,
            (
                (singles + 2*doubles + 3*triples + 4*hr)::DOUBLE / NULLIF(ab, 0)
                - h::DOUBLE / NULLIF(ab, 0)
            ) AS iso,
            (h - hr)::DOUBLE / NULLIF(ab - so - hr + sf, 0) AS babip
        FROM batter_game_logs
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW pitcher_game_logs_enriched AS
        SELECT
            *,
            ip_outs::DOUBLE / 3.0 AS ip,
            so * 9.0 / NULLIF(ip_outs / 3.0, 0) AS k_per_9,
            bb * 9.0 / NULLIF(ip_outs / 3.0, 0) AS bb_per_9,
            hr * 9.0 / NULLIF(ip_outs / 3.0, 0) AS hr_per_9,
            so::DOUBLE / NULLIF(bb, 0) AS k_per_bb,
            so::DOUBLE / NULLIF(tbf, 0) AS k_pct,
            bb::DOUBLE / NULLIF(tbf, 0) AS bb_pct,
            (so - bb)::DOUBLE / NULLIF(tbf, 0) AS k_minus_bb_pct,
            er * 9.0 / NULLIF(ip_outs / 3.0, 0) AS era,
            (bb + h)::DOUBLE / NULLIF(ip_outs / 3.0, 0) AS whip,
            h::DOUBLE / NULLIF(tbf - bb - hbp - so - hr, 0) AS babip,
            whiffs::DOUBLE / NULLIF(pitches, 0) AS whiff_pct
        FROM pitcher_game_logs
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW batter_statcast_summary AS
        SELECT
            batter_id AS player_id,
            batter_name AS player_name,
            level,
            COUNT(*) AS bbe,
            AVG(launch_speed) AS avg_ev,
            MAX(launch_speed) AS max_ev,
            AVG(launch_angle) AS avg_la,
            SUM(CASE WHEN is_hard_hit THEN 1 ELSE 0 END) AS hard_hit,
            SUM(CASE WHEN is_hard_hit THEN 1 ELSE 0 END)::DOUBLE
                / NULLIF(COUNT(launch_speed), 0) AS hard_hit_pct
        FROM batted_ball_events
        GROUP BY batter_id, batter_name, level
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW pitcher_pitch_type_summary AS
        SELECT
            pitcher_id AS player_id,
            pitcher_name AS player_name,
            level,
            pitch_type,
            pitch_name,
            COUNT(*) AS pitches,
            AVG(start_speed) AS avg_velocity,
            MAX(start_speed) AS max_velocity,
            AVG(spin_rate) AS avg_spin_rate,
            SUM(CASE WHEN is_whiff THEN 1 ELSE 0 END) AS whiffs,
            SUM(CASE WHEN is_whiff THEN 1 ELSE 0 END)::DOUBLE / NULLIF(COUNT(*), 0) AS whiff_pct
        FROM pitch_events
        GROUP BY pitcher_id, pitcher_name, level, pitch_type, pitch_name
        """
    )


def reload_date(
    con: "duckdb.DuckDBPyConnection",
    table_name: str,
    df: pd.DataFrame,
    game_date: date,
    columns: list[str],
) -> None:
    create_tables(con)
    ordered = df.reindex(columns=columns)
    con.register("_reload_df", ordered)
    con.execute(f"DELETE FROM {table_name} WHERE game_date = ?", [game_date])
    if not ordered.empty:
        con.execute(f"INSERT INTO {table_name} SELECT * FROM _reload_df")
    con.unregister("_reload_df")


def reload_game_log_date(
    con: "duckdb.DuckDBPyConnection",
    batters: pd.DataFrame,
    pitchers: pd.DataFrame,
    game_date: date,
) -> None:
    reload_date(con, "batter_game_logs", batters, game_date, BATTER_COLUMNS)
    reload_date(con, "pitcher_game_logs", pitchers, game_date, PITCHER_COLUMNS)
    create_views(con)


def reload_warehouse_date(
    con: "duckdb.DuckDBPyConnection",
    batters: pd.DataFrame,
    pitchers: pd.DataFrame,
    pitch_events: pd.DataFrame,
    batted_balls: pd.DataFrame,
    game_date: date,
) -> None:
    reload_date(con, "batter_game_logs", batters, game_date, BATTER_COLUMNS)
    reload_date(con, "pitcher_game_logs", pitchers, game_date, PITCHER_COLUMNS)
    reload_date(con, "pitch_events", pitch_events, game_date, PITCH_EVENT_COLUMNS)
    reload_date(con, "batted_ball_events", batted_balls, game_date, BATTED_BALL_COLUMNS)
    create_views(con)

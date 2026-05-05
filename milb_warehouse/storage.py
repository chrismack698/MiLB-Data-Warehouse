from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from .constants import (
    BATTED_BALL_COLUMNS,
    BATTER_COLUMNS,
    PITCHER_COLUMNS,
    PITCH_EVENT_COLUMNS,
    PLAYER_COLUMNS,
)

if TYPE_CHECKING:
    import duckdb


TABLE_ID_COLUMNS = {
    "batter_game_logs": "batter_game_log_id",
    "pitcher_game_logs": "pitcher_game_log_id",
    "pitch_events": "pitch_event_id",
    "batted_ball_events": "batted_ball_event_id",
}


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
        CREATE TABLE IF NOT EXISTS players (
            player_id INTEGER,
            player_name VARCHAR,
            birth_date DATE,
            birth_city VARCHAR,
            birth_state_province VARCHAR,
            birth_country VARCHAR,
            height VARCHAR,
            weight INTEGER,
            active BOOLEAN,
            primary_position_code VARCHAR,
            primary_position_name VARCHAR,
            primary_position_type VARCHAR,
            primary_position_abbreviation VARCHAR,
            bats VARCHAR,
            throws VARCHAR,
            draft_year INTEGER,
            mlb_debut_date DATE,
            name_slug VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS batter_game_logs (
            batter_game_log_id BIGINT,
            player_id INTEGER,
            player_name VARCHAR,
            game_pk INTEGER,
            game_date DATE,
            season INTEGER,
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
            pitcher_game_log_id BIGINT,
            player_id INTEGER,
            player_name VARCHAR,
            game_pk INTEGER,
            game_date DATE,
            season INTEGER,
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
            pitch_event_id BIGINT,
            game_pk INTEGER,
            game_date DATE,
            season INTEGER,
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
            batted_ball_event_id BIGINT,
            game_pk INTEGER,
            game_date DATE,
            season INTEGER,
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
    migrate_tables(con)
    create_views(con)


def migrate_tables(con: "duckdb.DuckDBPyConnection") -> None:
    for column in PLAYER_COLUMNS:
        if column in {"player_id", "weight", "draft_year"}:
            column_type = "INTEGER"
        elif column in {"birth_date", "mlb_debut_date"}:
            column_type = "DATE"
        elif column == "active":
            column_type = "BOOLEAN"
        else:
            column_type = "VARCHAR"
        con.execute(f"ALTER TABLE players ADD COLUMN IF NOT EXISTS {column} {column_type}")

    for table_name, id_column in TABLE_ID_COLUMNS.items():
        con.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {id_column} BIGINT")
        con.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS season INTEGER")
        con.execute(
            f"""
            UPDATE {table_name}
            SET season = YEAR(game_date)
            WHERE season IS NULL
              AND game_date IS NOT NULL
            """
        )
        con.execute(
            f"""
            WITH
            max_existing AS (
                SELECT COALESCE(MAX({id_column}), 0) AS max_id
                FROM {table_name}
            ),
            numbered AS (
                SELECT
                    rowid AS rid,
                    ROW_NUMBER() OVER (ORDER BY game_date, game_pk, rowid) AS rn
                FROM {table_name}
                WHERE {id_column} IS NULL
            )
            UPDATE {table_name} AS t
            SET {id_column} = n.rn + m.max_id
            FROM numbered AS n, max_existing AS m
            WHERE t.rowid = n.rid
            """
        )


def create_views(con: "duckdb.DuckDBPyConnection") -> None:
    batter_log_columns = ",\n            ".join(f"b.{column}" for column in BATTER_COLUMNS)
    pitcher_log_columns = ",\n            ".join(f"pgl.{column}" for column in PITCHER_COLUMNS)

    con.execute(
        f"""
        CREATE OR REPLACE VIEW batter_game_logs_enriched AS
        SELECT
            {batter_log_columns},
            DATE_DIFF('year', p.birth_date, b.game_date)
                - CASE
                    WHEN MONTH(b.game_date) < MONTH(p.birth_date)
                      OR (
                        MONTH(b.game_date) = MONTH(p.birth_date)
                        AND DAY(b.game_date) < DAY(p.birth_date)
                      )
                    THEN 1
                    ELSE 0
                  END AS player_age,
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
        FROM batter_game_logs AS b
        LEFT JOIN players AS p
            ON b.player_id = p.player_id
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE VIEW pitcher_game_logs_enriched AS
        SELECT
            {pitcher_log_columns},
            DATE_DIFF('year', p.birth_date, pgl.game_date)
                - CASE
                    WHEN MONTH(pgl.game_date) < MONTH(p.birth_date)
                      OR (
                        MONTH(pgl.game_date) = MONTH(p.birth_date)
                        AND DAY(pgl.game_date) < DAY(p.birth_date)
                      )
                    THEN 1
                    ELSE 0
                  END AS player_age,
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
        FROM pitcher_game_logs AS pgl
        LEFT JOIN players AS p
            ON pgl.player_id = p.player_id
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW batter_statcast_summary AS
        SELECT
            season,
            bbe.batter_id AS player_id,
            bbe.batter_name AS player_name,
            MAX(
                DATE_DIFF('year', p.birth_date, bbe.game_date)
                - CASE
                    WHEN MONTH(bbe.game_date) < MONTH(p.birth_date)
                      OR (
                        MONTH(bbe.game_date) = MONTH(p.birth_date)
                        AND DAY(bbe.game_date) < DAY(p.birth_date)
                      )
                    THEN 1
                    ELSE 0
                  END
            ) AS player_age,
            level,
            COUNT(*) AS bbe,
            AVG(launch_speed) AS avg_ev,
            MAX(launch_speed) AS max_ev,
            AVG(launch_angle) AS avg_la,
            SUM(CASE WHEN is_hard_hit THEN 1 ELSE 0 END) AS hard_hit,
            SUM(CASE WHEN is_hard_hit THEN 1 ELSE 0 END)::DOUBLE
                / NULLIF(COUNT(launch_speed), 0) AS hard_hit_pct
        FROM batted_ball_events AS bbe
        LEFT JOIN players AS p
            ON bbe.batter_id = p.player_id
        GROUP BY season, bbe.batter_id, bbe.batter_name, level
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW pitcher_pitch_type_summary AS
        SELECT
            season,
            pe.pitcher_id AS player_id,
            pe.pitcher_name AS player_name,
            MAX(
                DATE_DIFF('year', p.birth_date, pe.game_date)
                - CASE
                    WHEN MONTH(pe.game_date) < MONTH(p.birth_date)
                      OR (
                        MONTH(pe.game_date) = MONTH(p.birth_date)
                        AND DAY(pe.game_date) < DAY(p.birth_date)
                      )
                    THEN 1
                    ELSE 0
                  END
            ) AS player_age,
            level,
            pitch_type,
            pitch_name,
            COUNT(*) AS pitches,
            AVG(start_speed) AS avg_velocity,
            MAX(start_speed) AS max_velocity,
            AVG(spin_rate) AS avg_spin_rate,
            SUM(CASE WHEN is_whiff THEN 1 ELSE 0 END) AS whiffs,
            SUM(CASE WHEN is_whiff THEN 1 ELSE 0 END)::DOUBLE / NULLIF(COUNT(*), 0) AS whiff_pct
        FROM pitch_events AS pe
        LEFT JOIN players AS p
            ON pe.pitcher_id = p.player_id
        GROUP BY season, pe.pitcher_id, pe.pitcher_name, level, pitch_type, pitch_name
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
    id_column = TABLE_ID_COLUMNS[table_name]
    ordered = df.reindex(columns=columns)
    con.register("_reload_df", ordered)
    if ordered.empty:
        con.execute(f"DELETE FROM {table_name} WHERE game_date = ?", [game_date])
    else:
        max_id = con.execute(f"SELECT COALESCE(MAX({id_column}), 0) FROM {table_name}").fetchone()[0]
        con.execute(
            f"""
            DELETE FROM {table_name}
            WHERE game_date = ?
               OR game_pk IN (SELECT DISTINCT game_pk FROM _reload_df)
            """,
            [game_date],
        )
        insert_columns = ", ".join([id_column, *columns])
        select_columns = ", ".join(columns)
        if "at_bat_index" in columns:
            order_columns = "game_date, game_pk, at_bat_index, event_index"
        else:
            order_columns = "game_date, game_pk, team_name, player_name"
        con.execute(
            f"""
            INSERT INTO {table_name} ({insert_columns})
            SELECT
                {int(max_id)} + ROW_NUMBER() OVER (
                    ORDER BY {order_columns}
                ) AS {id_column},
                {select_columns}
            FROM _reload_df
            """
        )
    con.unregister("_reload_df")


def upsert_players(con: "duckdb.DuckDBPyConnection", players: pd.DataFrame) -> None:
    create_tables(con)
    ordered = players.reindex(columns=PLAYER_COLUMNS)
    if ordered.empty:
        return

    ordered = ordered.drop_duplicates(subset=["player_id"], keep="last")
    con.register("_players_df", ordered)
    columns = ", ".join(PLAYER_COLUMNS)
    con.execute(
        """
        DELETE FROM players
        WHERE player_id IN (SELECT player_id FROM _players_df)
        """
    )
    con.execute(
        f"""
        INSERT INTO players ({columns})
        SELECT {columns}
        FROM _players_df
        """
    )
    con.unregister("_players_df")


def existing_fact_player_ids(con: "duckdb.DuckDBPyConnection") -> list[int]:
    create_tables(con)
    rows = con.execute(
        """
        SELECT DISTINCT player_id
        FROM (
            SELECT player_id FROM batter_game_logs
            UNION ALL
            SELECT player_id FROM pitcher_game_logs
            UNION ALL
            SELECT batter_id AS player_id FROM pitch_events
            UNION ALL
            SELECT pitcher_id AS player_id FROM pitch_events
            UNION ALL
            SELECT batter_id AS player_id FROM batted_ball_events
            UNION ALL
            SELECT pitcher_id AS player_id FROM batted_ball_events
        )
        WHERE player_id IS NOT NULL
        ORDER BY player_id
        """
    ).fetchall()
    return [int(row[0]) for row in rows]


def reload_game_log_date(
    con: "duckdb.DuckDBPyConnection",
    players: pd.DataFrame,
    batters: pd.DataFrame,
    pitchers: pd.DataFrame,
    game_date: date,
) -> None:
    upsert_players(con, players)
    reload_date(con, "batter_game_logs", batters, game_date, BATTER_COLUMNS)
    reload_date(con, "pitcher_game_logs", pitchers, game_date, PITCHER_COLUMNS)
    create_views(con)


def reload_warehouse_date(
    con: "duckdb.DuckDBPyConnection",
    players: pd.DataFrame,
    batters: pd.DataFrame,
    pitchers: pd.DataFrame,
    pitch_events: pd.DataFrame,
    batted_balls: pd.DataFrame,
    game_date: date,
) -> None:
    upsert_players(con, players)
    reload_date(con, "batter_game_logs", batters, game_date, BATTER_COLUMNS)
    reload_date(con, "pitcher_game_logs", pitchers, game_date, PITCHER_COLUMNS)
    reload_date(con, "pitch_events", pitch_events, game_date, PITCH_EVENT_COLUMNS)
    reload_date(con, "batted_ball_events", batted_balls, game_date, BATTED_BALL_COLUMNS)
    create_views(con)

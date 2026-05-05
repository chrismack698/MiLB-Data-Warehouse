from __future__ import annotations

import json
from hashlib import sha1
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

from .constants import BASE_URL, LIVE_URL, STATIC_WHIFF_CODES


class StatsApiClient:
    def __init__(
        self,
        cache_dir: Path,
        delay: float = 0.15,
        force_refresh: bool = False,
        request_timeout: float = 15.0,
        retries: int = 3,
    ) -> None:
        self.cache_dir = cache_dir
        self.delay = delay
        self.force_refresh = force_refresh
        self.request_timeout = request_timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "milb-stats-warehouse/0.1"})

    def request_json(self, url: str, cache_path: Path) -> dict[str, Any]:
        if cache_path.exists() and not self.force_refresh:
            return json.loads(cache_path.read_text(encoding="utf-8"))

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        last_error: Exception | None = None

        for attempt in range(1, self.retries + 1):
            try:
                response = self.session.get(url, timeout=(5, self.request_timeout))
                response.raise_for_status()
                data = response.json()
                tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
                tmp_path.write_text(json.dumps(data), encoding="utf-8")
                tmp_path.replace(cache_path)
                if self.delay:
                    time.sleep(self.delay)
                return data
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(2 ** (attempt - 1), 8))

        raise RuntimeError(f"Failed after {self.retries} attempts: {url}") from last_error

    def schedule(self, sport_id: int, game_date: date) -> list[dict[str, Any]]:
        url = (
            f"{BASE_URL}/schedule?sportId={sport_id}"
            f"&date={game_date.isoformat()}&gameType=R&hydrate=team,venue"
        )
        cache_path = self.cache_dir / "schedules" / f"{sport_id}_{game_date}.json"
        data = self.request_json(url, cache_path)
        games: list[dict[str, Any]] = []
        for day in data.get("dates", []):
            games.extend(day.get("games", []))
        return games

    def live_game(self, game_pk: int) -> dict[str, Any]:
        url = f"{LIVE_URL}/game/{game_pk}/feed/live"
        cache_path = self.cache_dir / "games" / f"{game_pk}.json"
        return self.request_json(url, cache_path)

    def people(self, player_ids: list[int]) -> list[dict[str, Any]]:
        if not player_ids:
            return []

        ids = sorted(set(player_ids))
        id_string = ",".join(str(player_id) for player_id in ids)
        cache_key = sha1(id_string.encode("utf-8")).hexdigest()
        url = f"{BASE_URL}/people?personIds={id_string}"
        cache_path = self.cache_dir / "metadata" / "people" / f"{cache_key}.json"
        data = self.request_json(url, cache_path)
        return data.get("people", [])

    def whiff_codes(self) -> set[str]:
        url = f"{BASE_URL}/pitchCodes"
        cache_path = self.cache_dir / "metadata" / "pitch_codes.json"
        try:
            data = self.request_json(url, cache_path)
        except RuntimeError:
            return set(STATIC_WHIFF_CODES)

        return {
            item["code"]
            for item in data
            if item.get("code")
            and item.get("pitchStatus")
            and item.get("swingMissStatus")
        } or set(STATIC_WHIFF_CODES)

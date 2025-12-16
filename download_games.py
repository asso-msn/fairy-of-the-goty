import time
from argparse import ArgumentParser
from datetime import datetime

import yaml
from requests_cache import CachedSession

from app import DATA_DIR, VAR_DIR
from app.config import config
from app.igdb import API
from app.models.game import Game

fields = (
    "name",
    # "summary",
    "slug",
    "rating",
    "genres.name",
    "platforms.name",
    "first_release_date",
    "cover.url",
    "involved_companies.company.name",
)


def from_igdb_data(data: dict) -> Game:
    result = {}
    for field in fields:
        parts = field.split(".")
        value = data
        for part in parts:
            if isinstance(value, list):
                value = [
                    item.get(part)
                    for item in value
                    if item.get(part) is not None
                ]
            else:
                value = value.get(part)
            if value is None:
                break
        if value is not None:
            result[parts[0]] = value
    return Game(**result)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("year", type=int, nargs="?", default=config.year)
    parser.add_argument(
        "--stop-at", type=int, default=-1, help="Stop after N fetched games"
    )
    args = parser.parse_args()

    api = API(
        config.igdb.client_id,
        config.igdb.client_secret,
        session=CachedSession(
            VAR_DIR / "igdb_cache", allowable_methods=("POST",)
        ),
    )

    start_of_year_unix = int(datetime(args.year, 1, 1).timestamp())
    end_of_year_unix = int(datetime(args.year, 12, 31, 23, 59, 59).timestamp())

    stop_at = args.stop_at
    results = []
    limit = 500
    page = 0
    sleep = 1

    limit = min(limit, stop_at) if stop_at >= 0 else limit
    while True:
        result = api.request(
            "games",
            f"fields {', '.join(fields)}",
            "where "
            + (
                "game_type = ("
                f"{API.Game.Category.MAIN_GAME}, {API.Game.Category.EXPANDED}"
                ")"
                f"& release_dates.date >= {start_of_year_unix}"
                f"& release_dates.date <= {end_of_year_unix}"
                # "& parent_game = null"
                "& version_parent = null"
            ),
            f"limit {limit}",
            f"offset {limit * page}",
        )
        if not result:
            break
        results.extend([from_igdb_data(item) for item in result])
        print(f"Fetched {len(results)} games ({page=}), sleeping {sleep}s...")
        if (stop_at >= 0 and len(results) >= stop_at) or len(result) < limit:
            break
        page += 1
        time.sleep(sleep)

    with config.get_games_path(args.year).open("w") as f:
        yaml.dump([x.model_dump(exclude_unset=True) for x in results], f)

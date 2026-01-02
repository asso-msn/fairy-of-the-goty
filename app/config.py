import secrets
from datetime import datetime

import yaml
from pydantic import BaseModel, Field

from app import DATA_DIR, VAR_DIR

SECRET_KEY_FILE = VAR_DIR / "secret_key.txt"
CONFIG_FILE = DATA_DIR / "config.yml"


class Config(BaseModel):
    class Discord(BaseModel):
        client_id: str | None = Field(None, coerce_numbers_to_str=True)
        client_secret: str | None = None
        server_id: str | None = Field(None, coerce_numbers_to_str=True)

    class IGDB(BaseModel):
        client_id: str | None = None
        client_secret: str | None = None

    discord: Discord = Discord()
    igdb: IGDB = IGDB()

    votes_per_user: int = 3
    votes_per_genre_per_user: dict[str, int] = {"Music": 1}
    year: int = datetime.now().year
    disable_voting: bool = False
    allow_viewing_results: bool = False

    def get_games_path(self, year=None) -> str:
        year = year or self.year
        return DATA_DIR / f"goty_{year}_games.yml"


if not SECRET_KEY_FILE.exists():
    secret_key = secrets.token_hex(32)
    SECRET_KEY_FILE.write_text(secret_key)
else:
    secret_key = SECRET_KEY_FILE.read_text().strip()

if not CONFIG_FILE.exists():
    config = Config().model_dump()
    with CONFIG_FILE.open("w") as f:
        yaml.dump(config, f)
else:
    with (DATA_DIR / "config.yml").open() as f:
        config = Config.model_validate(yaml.safe_load(f))

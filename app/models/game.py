import datetime
import html

from pydantic import BaseModel, Field, computed_field

from app.igdb import API

PLATFORM_NAMES = {"PC (Microsoft Windows)": "Windows"}


class ReleasePlatform(BaseModel):
    name: str


class ReleaseDate(BaseModel):
    date: datetime.date | None = None
    y: int | None = None
    platform: ReleasePlatform | None = None


class Game(BaseModel):
    name: str
    summary: str = None
    slug: str
    game_type: int | None = None
    rating: float = None
    genres: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    first_release_date: datetime.date | None = None
    release_dates: list[ReleaseDate] = Field(default_factory=list)
    cover: str = None
    involved_companies: list[str] = None

    def model_post_init(self, context):
        self.platforms = [
            PLATFORM_NAMES.get(p, p)
            for p in self.platforms
        ]
        if self.rating:
            self.rating = (self.rating * 100) // 100
        if self.slug in (
            "umamusume-pretty-derby",
            "deltarune",
        ):
            self.genres = [x for x in self.genres if x != "Music"]

    def get_release_labels(self, year: int) -> list[str]:
        if not self.first_release_date or self.first_release_date.year >= year:
            return []
        labels = []
        for release in self.release_dates:
            release_year = release.date.year if release.date else release.y
            if release_year == year and release.platform:
                platform = PLATFORM_NAMES.get(
                    release.platform.name, release.platform.name
                )
                label = f"{platform} ({year})"
                if label not in labels:
                    labels.append(label)
        return labels

    @computed_field
    @property
    def release_type(self) -> str:
        if self.game_type is None:
            return "normal"
        return API.Game.Category(self.game_type).display_name

    @computed_field
    @property
    def escaped_name(self) -> str:
        return (
            html.escape(self.name, quote=False)
            .replace("'", "\\'")
            .replace('"', "&quot;")
        )

    @computed_field
    @property
    def genres_html(self) -> str:
        return ", ".join(self.genres)

    @computed_field
    @property
    def cover_url(self) -> str | None:
        if self.cover:
            return "https:" + self.cover.replace("t_thumb", "t_cover_big")
        return (
            "https://images.igdb.com/igdb/image/upload/t_cover_big/nocover.png"
        )

    @computed_field
    @property
    def igdb_url(self) -> str:
        return f"https://www.igdb.com/games/{self.slug}"

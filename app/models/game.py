import datetime
import html

from pydantic import BaseModel, Field, computed_field


class Game(BaseModel):
    name: str
    summary: str = None
    slug: str
    rating: float = None
    genres: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    first_release_date: datetime.date = None
    cover: str = None
    involved_companies: list[str] = None

    def model_post_init(self, context):
        self.platforms = [
            {"PC (Microsoft Windows)": "Windows"}.get(p, p)
            for p in self.platforms
        ]
        if self.rating:
            self.rating = (self.rating * 100) // 100

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

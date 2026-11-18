import contextlib
import time

import flask
import yaml
from fastapi import FastAPI, HTTPException, Request
from a2wsgi import WSGIMiddleware
from fastapi.responses import JSONResponse
from flask import Flask
from pydantic import BaseModel

from app import DATA_DIR, discord, search, votes
from app.config import config, secret_key
from app.models.game import Game

front = Flask(__name__, template_folder="templates")
front.debug = True
front.config["SECRET_KEY"] = secret_key
front.config["TEMPLATES_AUTO_RELOAD"] = True
front.config["DEBUG"] = True
app = FastAPI()
api = FastAPI()

app.mount("/api", api)
app.mount("/", WSGIMiddleware(front))


@front.context_processor
def flask_globals():
    result = {}
    result["config"] = config
    if config.discord.client_id and config.discord.client_secret:
        result["discord_auth_url"] = discord.get_authorization_url(
            client_id=config.discord.client_id,
            redirect_uri=flask.url_for("discord_callback", _external=True),
        )
    access_token = flask.session.get("discord_access_token")
    if access_token:
        result["discord_access_token"] = access_token
        discord_api = discord.API(access_token=access_token)
        discord_user = discord_api.get_user()
        result["discord_user"] = discord_user
        result["user_votes"] = votes.get_user_votes(user_id=discord_user.id)

    return result


@contextlib.contextmanager
def timed(title=None):
    now = time.monotonic()
    if title:
        print(f"Starting {title}...")
    try:
        yield
    finally:
        print(title or "Task", f"done in {time.monotonic() - now}s")


def load_game_overrides():
    path = DATA_DIR / "overrides.yml"
    if not path.exists():
        return {}
    with path.open() as f:
        overrides = yaml.safe_load(f)
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise ValueError("Game overrides must be a mapping")
    if any(not isinstance(key, str) for key in overrides):
        raise ValueError("Game override names must be strings")
    unsupported = sorted(set(overrides) - {"add_genres", "force_year"})
    if unsupported:
        raise ValueError(
            f"Unsupported game override(s): {', '.join(unsupported)}"
        )
    add_genres = overrides.get("add_genres", {})
    if not isinstance(add_genres, dict):
        raise ValueError("add_genres must be a mapping of game slugs to genres")
    for slug, genres in add_genres.items():
        if not isinstance(slug, str) or not slug:
            raise ValueError("add_genres keys must be non-empty game slugs")
        if not isinstance(genres, list) or any(
            not isinstance(genre, str) or not genre for genre in genres
        ):
            raise ValueError(
                f"Genres for {slug} must be a list of non-empty strings"
            )
    force_year = overrides.get("force_year", {})
    if not isinstance(force_year, dict):
        raise ValueError("force_year must be a mapping of game slugs to years")
    for slug, year in force_year.items():
        if not isinstance(slug, str) or not slug:
            raise ValueError("force_year keys must be non-empty game slugs")
        if not isinstance(year, int) or isinstance(year, bool):
            raise ValueError(f"Year for {slug} must be an integer")
    return {"add_genres": add_genres, "force_year": force_year}


def load_games(year):
    with config.get_games_path(year).open() as f:
        games = {
            game["name"]: Game(**game) for game in yaml.safe_load(f)
        }
    overrides = load_game_overrides()
    force_year = overrides["force_year"]
    games = {
        name: game
        for name, game in games.items()
        if game.slug not in force_year or force_year[game.slug] == year
    }
    add_genres = overrides["add_genres"]
    for game in games.values():
        for genre in add_genres.get(game.slug, []):
            if genre not in game.genres:
                game.genres.append(genre)
    return games


def get_games_by_year(year):
    if year not in games_by_year:
        games_by_year[year] = load_games(year)
    return games_by_year[year]


with timed("Loading games from file"):
    votes.archive_legacy_votes(config.year)
    games_by_year = {config.year: load_games(config.year)}
    games_by_name = games_by_year[config.year]


@front.route("/")
def index():
    return flask.render_template("index.html.j2")


@front.route("/results/")
@front.route("/results/<genre>")
def results(genre=None):
    return render_results(config.year, genre)


@front.route("/<int:year>/results/")
@front.route("/<int:year>/results/<genre>")
def historical_results(year, genre=None):
    if year >= config.year or not config.get_games_path(year).is_file():
        flask.abort(404)
    return render_results(year, genre, public=True)


def render_results(year, genre, public=False):
    if not public and not config.allow_viewing_results:
        return "Viewing results is not allowed", 403
    if genre:
        genre = genre.capitalize()
    games_for_year = get_games_by_year(year)
    votes_data = votes.load(year=year) if public else votes.load()
    votes_by_game = {}
    voting_users = set()
    with discord.DB_PATH.open() as f:
        users_data = yaml.safe_load(f)
    for vote in votes_data:
        votes_by_game.setdefault(vote.game_name, [])
        votes_by_game[vote.game_name].append(vote)
        voting_users.add(users_data[vote.user_id])
    top = votes.get_top(
        genre=genre,
        votes_data=votes_data,
        games_by_name=games_for_year,
    )
    result = [
        {
            "votes": [
                users_data[vote.user_id]
                for vote in votes_by_game[game]
                if not vote.hidden
            ],
            "score": score,
            "game": games_for_year[game],
        }
        for game, score in top
    ]
    return flask.render_template(
        "results.html.j2",
        data=result,
        category=genre or "Free",
        year=year,
        results_path=f"/{year}/results" if public else "/results",
        stats={"participants": len(voting_users)},
    )


@front.route("/auth/discord/callback")
def discord_callback():
    code = flask.request.args.get("code")
    if not code:
        raise Exception("Missing code parameter from Discord")
    token_response = discord.get_discord_token(
        client_id=config.discord.client_id,
        client_secret=config.discord.client_secret,
        redirect_uri=flask.url_for("discord_callback", _external=True),
        code=code,
    )
    flask.session["discord_access_token"] = token_response.access_token
    return flask.redirect(flask.url_for("index"))


@front.route("/auth/discord/logout")
def discord_logout():
    token = flask.session.pop("discord_access_token", None)
    # if token:
    #     discord.revoke_token(
    #         client_id=config.discord.client_id,
    #         client_secret=config.discord.client_secret,
    #         token=token,
    #     )
    return flask.redirect(flask.url_for("index"))


@api.exception_handler(Exception)
async def api_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"message": f"{exc}"},
    )


@api.get("/games/")
def api_games(q: str):
    if not q:
        return []
    matches = search.find_matches(q, games_by_name.keys())
    print(f"Matches for {q}: {matches}")
    return [
        {
            **games_by_name[result[0]].model_dump(),
            "year_releases": games_by_name[result[0]].get_release_labels(
                config.year
            ),
        }
        for result in matches
    ]


class VoteBody(BaseModel):
    game_name: str
    discord_access_token: str | None = None


def get_discord_user(access_token: str | None):
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Discord authentication required",
        )
    discord_api = discord.API(access_token=access_token)
    return discord_api.get_user()


@api.post("/vote/")
def add_vote(
    body: VoteBody,
):
    if config.disable_voting:
        raise Exception("Voting is currently disabled")
    discord_user = get_discord_user(body.discord_access_token)
    user_id = discord_user.id

    votes.add(
        game_name=body.game_name,
        user_id=user_id,
    )


class PatchVoteBody(BaseModel):
    game_name: str
    discord_access_token: str | None = None
    hidden: bool


@api.patch("/vote/")
def patch_vote(
    body: PatchVoteBody,
):
    if config.disable_voting:
        raise Exception("Voting is currently disabled")
    discord_user = get_discord_user(body.discord_access_token)
    user_id = discord_user.id

    votes.set_hidden(
        game_name=body.game_name,
        user_id=user_id,
        hidden=body.hidden,
    )


@api.delete("/vote/")
def add_vote(
    body: VoteBody,
):
    if config.disable_voting:
        raise Exception("Voting is currently disabled")
    discord_user = get_discord_user(body.discord_access_token)
    user_id = discord_user.id

    votes.delete(
        game_name=body.game_name,
        user_id=user_id,
    )

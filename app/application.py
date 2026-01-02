import contextlib
import time

import flask
import rapidfuzz
import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.responses import JSONResponse
from flask import Flask
from pydantic import BaseModel

from app import discord, votes
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


with timed("Loading games from file"):
    with config.get_games_path().open() as f:
        games_by_name = {
            game["name"]: Game(**game) for game in yaml.safe_load(f)
        }


@front.route("/")
def index():
    return flask.render_template("index.html.j2")


@front.route("/results/")
@front.route("/results/<genre>")
def results(genre=None):
    if not config.allow_viewing_results:
        return "Viewing results is not allowed", 403
    if genre:
        genre = genre.capitalize()
    votes_data = votes.load()
    votes_by_game = {}
    voting_users = set()
    with discord.DB_PATH.open() as f:
        users_data = yaml.safe_load(f)
    for vote in votes_data:
        votes_by_game.setdefault(vote.game_name, [])
        votes_by_game[vote.game_name].append(vote)
        voting_users.add(users_data[vote.user_id])
    top = votes.get_top(genre=genre)
    result = [
        {
            "votes": [
                users_data[vote.user_id]
                for vote in votes_by_game[game]
                if not vote.hidden
            ],
            "score": score,
            "game": games_by_name[game],
        }
        for game, score in top
    ]
    return flask.render_template(
        "results.html.j2",
        data=result,
        category=genre or "Free",
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
    matches = rapidfuzz.process.extract(
        q,
        games_by_name.keys(),
        scorer=rapidfuzz.fuzz.WRatio,
        processor=rapidfuzz.utils.default_process,
        limit=12,
    )
    print(f"Matches for {q}: {matches}")
    return [games_by_name[result[0]].model_dump() for result in matches]


class VoteBody(BaseModel):
    game_name: str
    discord_access_token: str


@api.post("/vote/")
def add_vote(
    body: VoteBody,
):
    if config.disable_voting:
        raise Exception("Voting is currently disabled")
    discord_api = discord.API(access_token=body.discord_access_token)
    discord_user = discord_api.get_user()
    user_id = discord_user.id

    votes.add(
        game_name=body.game_name,
        user_id=user_id,
    )


class PatchVoteBody(BaseModel):
    game_name: str
    discord_access_token: str
    hidden: bool


@api.patch("/vote/")
def patch_vote(
    body: PatchVoteBody,
):
    if config.disable_voting:
        raise Exception("Voting is currently disabled")
    discord_api = discord.API(access_token=body.discord_access_token)
    discord_user = discord_api.get_user()
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
    discord_api = discord.API(access_token=body.discord_access_token)
    discord_user = discord_api.get_user()
    user_id = discord_user.id

    votes.delete(
        game_name=body.game_name,
        user_id=user_id,
    )

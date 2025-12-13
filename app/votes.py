import datetime

import yaml
from pydantic import BaseModel, Field

from app import VAR_DIR, application
from app.config import config
from app.models.game import Game

DB_PATH = VAR_DIR / "votes.yml"


class Vote(BaseModel):
    game_name: str
    user_id: str = Field(coerce_numbers_to_str=True)
    hidden: bool = False
    time: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


def load():
    if not DB_PATH.exists():
        return []
    with DB_PATH.open() as f:
        return [Vote(**item) for item in yaml.safe_load(f)]


def save(votes):
    with DB_PATH.open("w") as f:
        yaml.dump([vote.model_dump() for vote in votes], f)


def add(game_name: str, user_id: str):
    votes = load()
    game = application.games_by_name[game_name]
    user_votes = get_user_votes(user_id, votes=votes)
    vote_genre = None
    for genre in game.genres:
        if genre in config.votes_per_genre_per_user.keys():
            vote_genre = genre
            break
    if vote_genre:
        if user_votes["genres"][vote_genre]["remaining"] == 0:
            raise Exception(f"No more votes available for {vote_genre}")
    elif user_votes["remaining"] == 0:
        raise Exception("No more votes available for free section")
    vote = Vote(game_name=game_name, user_id=user_id)
    print("New vote", vote)
    votes.append(vote)
    save(votes)


def delete(game_name: str, user_id: str):
    votes = load()
    for index, vote in enumerate(votes):
        if vote.game_name == game_name and vote.user_id == user_id:
            del votes[index]
            break
    else:
        Exception(f"Could not find existing vote for game {game_name}")
    save(votes)


def set_hidden(game_name: str, user_id: str, hidden: bool):
    votes = load()
    for vote in votes:
        if vote.game_name == game_name and vote.user_id == user_id:
            vote.hidden = hidden
            break
    else:
        Exception(f"Could not find existing vote for game {game_name}")
    save(votes)


def get_user_votes(user_id: str, votes=None):
    def build_vote(vote: Vote):
        return {
            "game": application.games_by_name[vote.game_name],
            "time": vote.time,
            "hidden": vote.hidden,
        }

    votes = votes or load()
    user_votes = [build_vote(vote) for vote in votes if vote.user_id == user_id]
    user_votes_all = [
        vote
        for vote in user_votes
        if not any(
            genre in config.votes_per_genre_per_user.keys()
            for genre in vote["game"].genres
        )
    ]
    user_votes_genres = {
        genre: [vote for vote in user_votes if genre in vote["game"].genres]
        for genre in config.votes_per_genre_per_user.keys()
    }
    return {
        "votes": user_votes_all,
        "remaining": config.votes_per_user - len(user_votes_all),
        "genres": {
            genre: {
                "votes": votes,
                "remaining": (
                    config.votes_per_genre_per_user[genre] - len(votes)
                ),
            }
            for genre, votes in user_votes_genres.items()
        },
    }

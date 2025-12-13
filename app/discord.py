import logging
import typing as t
import urllib
from pathlib import Path

import requests
import yaml
from pydantic import BaseModel as Model
from requests import Session

from app import VAR_DIR

DB_PATH = VAR_DIR / "discord.yml"
BASE_URL = "https://discord.com"
API_URL = f"{BASE_URL}/api/v10"
CDN_URL = "https://cdn.discordapp.com"
SCOPES = ("email", "identify")

session = Session()
session.headers["Content-Type"] = "application/x-www-form-urlencoded"


class AuthorizationParams(Model):
    client_id: str
    redirect_uri: str
    response_type: str = "code"
    scope: str = " ".join(SCOPES)
    state: str | None
    prompt: str = "none"


def get_authorization_url(client_id: str, redirect_uri: str, state: str = None):
    url = "https://discord.com/oauth2/authorize"
    params = AuthorizationParams(
        client_id=client_id, state=state, redirect_uri=redirect_uri
    )
    return f"{url}?" + urllib.parse.urlencode(
        params.model_dump(exclude_none=True)
    )


def revoke_token(client_id: str, client_secret: str, token: str):
    url = f"{API_URL}/oauth2/token/revoke"
    response = session.post(
        url,
        data={"token": token},
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    logging.debug(response.text)
    response.raise_for_status()


class AccessTokenRequest(Model):
    grant_type: str = "authorization_code"
    code: str
    redirect_uri: str


class AccessTokenResponse(Model):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: str


def get_discord_token(
    client_id: str, client_secret: str, redirect_uri: str, code: str
) -> AccessTokenResponse:
    url = f"{API_URL}/oauth2/token"
    data = AccessTokenRequest(code=code, redirect_uri=redirect_uri)
    logging.debug(f"{url}, {data}")
    response = session.post(
        url,
        data=data.model_dump(),
        auth=(client_id, client_secret),
    )
    logging.debug(response.text)
    response.raise_for_status()
    return AccessTokenResponse(**response.json())


class RefreshTokenRequest(Model):
    grant_type: str = "refresh_token"
    refresh_token: str


class API:
    def __init__(self, access_token: str, bot=None):
        if not access_token:
            raise ValueError("Missing Discord access_token")

        self.access_token = access_token
        auth_type = "Bot" if bot else "Bearer"
        self._authorization_header = f"{auth_type} {access_token}"

    def request(self, method, url: str, data=None, **kwargs):
        api = kwargs.pop("api", True)
        base = API_URL if api else BASE_URL
        url = base + url
        logging.debug(
            f"{method}, {url}, {kwargs}, {data}, {self._authorization_header}"
        )
        response = requests.request(
            method,
            url,
            params=kwargs,
            json=data,
            headers={"Authorization": self._authorization_header},
        )
        logging.debug(response.text)
        response.raise_for_status()
        if not response.text:
            return
        return response.json()

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs):
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.request("DELETE", url, **kwargs)

    class User(Model):
        id: str
        username: str
        discriminator: str
        global_name: str | None
        avatar: str | None
        bot: bool | None = None
        system: bool | None = None
        mfa_enabled: bool | None
        banner: str | None
        accent_color: int | None
        locale: str | None
        verified: bool | None
        email: str | None
        flags: int | None
        premium_type: int | None
        public_flags: int | None
        avatar_decoration_data: dict | None

        def __str__(self):
            return self.name

        @property
        def name(self):
            return self.global_name or self.username

        @property
        def avatar_url(self):
            if not self.avatar:
                return None
            return f"{CDN_URL}/avatars/{self.id}" f"/{self.avatar}?size=256"

    def get_user(self) -> "API.User":
        data = self.get("/users/@me")
        result = self.User(**data)
        if not DB_PATH.exists():
            db = {}
        else:
            with open(DB_PATH, "r") as f:
                db = yaml.safe_load(f) or {}
        db[result.id] = result.name
        with open(DB_PATH, "w") as f:
            yaml.dump(db, f)
        return result

    def get_oauth(self):
        return self.get("/oauth2/@me")

    def get_bot(self):
        return self.get("/oauth2/applications/@me")

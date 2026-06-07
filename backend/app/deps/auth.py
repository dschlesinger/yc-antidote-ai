"""FastAPI auth dependency: validate Supabase access tokens."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client

from app.config import settings

_bearer = HTTPBearer(auto_error=False)
_supabase: Client = create_client(settings.supabase_url, settings.supabase_anon_key)


class AuthUser:
    """Authenticated user identity extracted from a Supabase JWT."""

    def __init__(self, user_id: str, email: str | None) -> None:
        self.id = user_id
        self.email = email


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthUser:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        resp = _supabase.auth.get_user(creds.credentials)
    except Exception as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from e
    user = resp.user if resp else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    return AuthUser(user_id=user.id, email=user.email)

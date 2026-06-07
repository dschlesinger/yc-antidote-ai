"""LiveKit session token endpoint."""

import uuid

from fastapi import APIRouter, HTTPException, status
from livekit.api import AccessToken, VideoGrants

from app.config import settings
from app.models.session import SessionTokenResponse

router = APIRouter(prefix="/api/session", tags=["session"])


@router.post("/token", response_model=SessionTokenResponse)
async def create_session_token() -> SessionTokenResponse:
    """Issue a LiveKit access token for a new participant."""
    room_name = f"antidote-{uuid.uuid4().hex[:8]}"
    participant_identity = f"user-{uuid.uuid4().hex[:6]}"

    try:
        token = (
            AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
            .with_identity(participant_identity)
            .with_grants(VideoGrants(room_join=True, room=room_name))
            .to_jwt()
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token generation failed: {e}",
        ) from e

    return SessionTokenResponse(token=token, room_name=room_name)

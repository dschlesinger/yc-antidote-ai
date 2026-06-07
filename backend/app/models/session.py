from pydantic import BaseModel


class SessionTokenResponse(BaseModel):
    """LiveKit access token for a new agent session."""
    token: str
    room_name: str
    livekit_url: str


class InterjectionEvent(BaseModel):
    """Emitted when the agent detects a factual discrepancy."""
    claim: str
    correction: str
    sources: list[dict]

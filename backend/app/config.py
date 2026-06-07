from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # LiveKit
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str

    # Minimax via OpenAI-compatible API
    minimax_api_key: str
    minimax_base_url: str = "https://api.minimax.chat/v1"
    minimax_model: str = "M3.0"

    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str

    # Moss
    moss_project_id: str
    moss_project_key: str
    moss_index_name: str = "antidote-due-diligence"

    # Unsiloed
    unsiloed_api_key: str
    unsiloed_api_url: str = "https://prod.visionapi.unsiloed.ai"


settings = Settings()

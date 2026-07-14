from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Radar Oylut"
    hours_window: int = 24
    request_timeout: float = 15.0
    max_items_per_source: int = 40
    similarity_threshold: int = 78
    model_config = SettingsConfigDict(env_prefix="RADAR_", env_file=".env")


settings = Settings()

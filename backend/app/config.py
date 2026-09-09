from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    use_simulated_data: bool = True
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:4173"]
    log_level: str = "INFO"
    api_version: str = "0.1.0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

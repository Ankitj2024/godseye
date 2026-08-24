"""God's Eye backend configuration via pydantic-settings."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # App
    app_name: str = "godseye"
    app_env: str = "development"
    debug: bool = True

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Storage — resolve relative to this file's parent (backend/)
    data_dir: str = "../data"

    # Upload limits (in MB)
    max_upload_size_mb: int = 5120  # 5 GB

    # CORS
    frontend_url: str = "http://localhost:5173"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def data_path(self) -> Path:
        """Resolve the data directory as an absolute path."""
        p = Path(self.data_dir)
        if not p.is_absolute():
            p = (Path(__file__).resolve().parent.parent / p).resolve()
        return p

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


# Singleton
settings = Settings()

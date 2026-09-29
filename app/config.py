"""Configuration lue depuis le fichier .env à la racine du projet."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


class Settings:
    # Enable Banking (agrégateur DSP2)
    eb_app_id: str = os.getenv("ENABLE_BANKING_APP_ID", "")
    eb_private_key_path: Path = ROOT / os.getenv("ENABLE_BANKING_KEY_PATH", "keys/private.pem")
    eb_redirect_url: str = os.getenv("ENABLE_BANKING_REDIRECT_URL", "http://localhost:8000/callback")
    eb_country: str = os.getenv("ENABLE_BANKING_COUNTRY", "FR")
    consent_days: int = int(os.getenv("CONSENT_DAYS", "180"))
    history_days: int = int(os.getenv("HISTORY_DAYS", "365"))

    # Classification LLM (optionnelle : sans clé, seules les règles s'appliquent)
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")

    # Stockage
    db_path: Path = ROOT / os.getenv("DB_PATH", "data/budget.db")

    @property
    def bank_enabled(self) -> bool:
        return bool(self.eb_app_id) and self.eb_private_key_path.exists()

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


settings = Settings()

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


@dataclass
class Settings:
    # Microsoft Graph
    ms_client_id: str = os.getenv("MS_CLIENT_ID", "")
    ms_tenant_id: str = os.getenv("MS_TENANT_ID", "common")
    ms_scopes: str = os.getenv("MS_SCOPES", "Mail.Read")
    # Storage
    db_path: str = os.getenv("OMA_DB_PATH", os.path.expanduser("~/.cache/outlook_mail_assistant/mail.db"))
    token_cache_path: str = os.getenv(
        "OMA_TOKEN_CACHE", os.path.expanduser("~/.cache/outlook_mail_assistant/token_cache.json")
    )
    # Summarization
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    openai_base_url: Optional[str] = os.getenv("OPENAI_BASE_URL")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    # Embeddings
    embeddings_enabled: bool = os.getenv("OMA_EMBEDDINGS", "false").lower() in {"1", "true", "yes"}
    openai_embedding_model: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    # Summarization options
    summary_max_tokens: int = int(os.getenv("OMA_SUMMARY_MAX_TOKENS", "256"))
    chunk_char_limit: int = int(os.getenv("OMA_CHUNK_CHAR_LIMIT", "6000"))


settings = Settings()

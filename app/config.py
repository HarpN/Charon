from __future__ import annotations

import os


class Settings:
    service_name: str = os.getenv("SERVICE_NAME", "charon-agent")
    service_version: str = os.getenv("SERVICE_VERSION", "0.1.0")
    agent_id: str = os.getenv("CHARON_AGENT_ID", "charon-v1")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8090"))

    judy_base_url: str = os.getenv("JUDY_BASE_URL", "http://judy-council:8000")
    judy_timeout_seconds: float = float(os.getenv("JUDY_TIMEOUT_SECONDS", "10"))

    signature_secret: str = os.getenv("CHARON_SIGNATURE_SECRET", "charon-dev-secret")
    signature_header: str = os.getenv("CHARON_SIGNATURE_HEADER", "X-Charon-Signature")


settings = Settings()

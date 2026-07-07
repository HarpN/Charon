from __future__ import annotations

import os


class Settings:
    service_name: str = os.getenv("SERVICE_NAME", "charon-agent")
    service_version: str = os.getenv("SERVICE_VERSION", "0.1.0")
    agent_id: str = os.getenv("CHARON_AGENT_ID", "charon-v1")
    host: str = os.getenv("HOST", "0.0.0.0")
    grpc_port: int = int(os.getenv("GRPC_PORT", "50051"))

    judy_grpc_target: str = os.getenv("JUDY_GRPC_TARGET", "judy-council:50052")
    judy_timeout_seconds: float = float(os.getenv("JUDY_TIMEOUT_SECONDS", "10"))
    judy_grpc_tls_enabled: bool = os.getenv("JUDY_GRPC_TLS_ENABLED", "false").lower() == "true"
    judy_grpc_ca_path: str = os.getenv("JUDY_GRPC_CA_PATH", "/etc/charon/tls/ca.crt")

    signature_secret: str = os.getenv("CHARON_SIGNATURE_SECRET", "charon-dev-secret")
    signature_header: str = os.getenv("CHARON_SIGNATURE_HEADER", "X-Charon-Signature")


settings = Settings()

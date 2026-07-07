from __future__ import annotations

import httpx

from .config import settings
from .models import ProposalPayload
from .signer import sign_payload


class JudyClient:
    def __init__(self) -> None:
        self._base = settings.judy_base_url.rstrip("/")
        self._timeout = settings.judy_timeout_seconds

    def send_proposal(self, proposal: ProposalPayload, commit: bool) -> dict:
        endpoint = "/proposals/commit" if commit else "/proposals/judge"
        payload = proposal.model_dump()
        signature = sign_payload(settings.signature_secret, payload)

        headers = {
            settings.signature_header: signature,
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(f"{self._base}{endpoint}", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

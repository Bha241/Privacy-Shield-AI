"""Local credential and secret detection kept independent of the ML model."""

from __future__ import annotations

import re

from pii_detector.schemas.entities import Entity


class CredentialRecognizer:
    """Detect high-risk credentials using conservative contextual patterns.

    This detector deliberately remains enabled when the optional semantic model
    is disabled. It prevents passwords, API keys, JWTs, and private keys from
    depending on a model that may not recognize secret-shaped values reliably.
    """

    _assignment = re.compile(
        r"(?i)\b(?P<label>password|passwd|pwd|secret|api[_ -]?key|x-api-key|access[_ -]?token|client[_ -]?secret)"
        r"\s*(?:is|=|:|=>)\s*[\"']?(?P<value>[A-Za-z0-9_./+=:@$%\-]{4,})"
    )
    _bearer = re.compile(r"(?i)\bBearer\s+(?P<value>[A-Za-z0-9._~+/=-]{12,})")
    _jwt = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
    _private_key = re.compile(r"-----BEGIN ([A-Z ]+PRIVATE KEY)-----[\s\S]+?-----END \1-----")

    _label_map = {
        "password": "PASSWORD",
        "passwd": "PASSWORD",
        "pwd": "PASSWORD",
        "secret": "CLIENT_SECRET",
        "api_key": "API_KEY",
        "api-key": "API_KEY",
        "apikey": "API_KEY",
        "x-api-key": "API_KEY",
        "access_token": "AUTH_BEARER_TOKEN",
        "access-token": "AUTH_BEARER_TOKEN",
        "client_secret": "CLIENT_SECRET",
        "client-secret": "CLIENT_SECRET",
    }

    def recognize(self, text: str) -> list[Entity]:
        entities: list[Entity] = []
        for match in self._assignment.finditer(text):
            value = match.group("value")
            start, end = match.span("value")
            label = self._label_map.get(match.group("label").lower().replace(" ", "_"), "SECRET")
            entities.append(Entity(value, label, start, end, 0.99, "credential_context"))

        for match in self._bearer.finditer(text):
            start, end = match.span("value")
            entities.append(Entity(match.group("value"), "AUTH_BEARER_TOKEN", start, end, 0.99, "credential_context"))

        for match in self._jwt.finditer(text):
            entities.append(Entity(match.group(), "JWT", match.start(), match.end(), 0.99, "credential_pattern"))

        for match in self._private_key.finditer(text):
            entities.append(Entity(match.group(), "PRIVATE_KEY", match.start(), match.end(), 1.0, "credential_pattern"))

        return entities

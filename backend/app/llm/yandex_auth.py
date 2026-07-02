"""Yandex Cloud auth: Api-Key or OAuth passport → IAM Bearer token."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

IAM_TOKEN_URL = "https://iam.api.cloud.yandex.net/iam/v1/tokens"


def yandex_credentials_configured(cfg: dict[str, Any]) -> bool:
    folder_id = str(cfg.get("yandex_folder_id", "")).strip()
    if not folder_id:
        return False
    return bool(
        str(cfg.get("yandex_api_key", "")).strip()
        or str(cfg.get("yandex_passport_token", "")).strip()
        or str(cfg.get("yandex_iam_token", "")).strip()
    )


class YandexAuth:
    """Build Authorization headers for Foundation Models API."""

    def __init__(
        self,
        *,
        api_key: str = "",
        passport_token: str = "",
        iam_token: str = "",
        folder_id: str = "",
    ) -> None:
        self._api_key = api_key.strip()
        self._passport_token = passport_token.strip()
        self._iam_token = iam_token.strip()
        self._folder_id = folder_id.strip()
        self._cached_iam: str = ""
        self._cached_iam_expires_at: float = 0.0

    def validate(self) -> None:
        if not self._folder_id:
            raise RuntimeError("YANDEX_FOLDER_ID is not configured")
        if not (self._api_key or self._passport_token or self._iam_token):
            raise RuntimeError(
                "YandexGPT auth missing: set YANDEX_API_KEY or YANDEX_PASSPORT_TOKEN in .env"
            )

    async def auth_headers(self) -> dict[str, str]:
        self.validate()
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Api-Key {self._api_key}"
            return headers

        iam = await self._resolve_iam_token()
        headers["Authorization"] = f"Bearer {iam}"
        if self._folder_id:
            headers["x-folder-id"] = self._folder_id
        return headers

    def auth_headers_sync(self) -> dict[str, str]:
        """Sync variant for startup probes (no running event loop)."""
        self.validate()
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Api-Key {self._api_key}"
            return headers

        iam = self._resolve_iam_token_sync()
        headers["Authorization"] = f"Bearer {iam}"
        if self._folder_id:
            headers["x-folder-id"] = self._folder_id
        return headers

    async def _resolve_iam_token(self) -> str:
        now = time.time()
        if self._cached_iam and now < self._cached_iam_expires_at - 60:
            return self._cached_iam

        if self._passport_token:
            token, expires_at = await self._exchange_passport_token(self._passport_token)
            self._cached_iam = token
            self._cached_iam_expires_at = expires_at
            return token

        if self._cached_iam and now < self._cached_iam_expires_at - 60:
            return self._cached_iam

        if self._iam_token:
            return self._iam_token

        raise RuntimeError("Yandex IAM token unavailable")

    def _resolve_iam_token_sync(self) -> str:
        now = time.time()
        if self._cached_iam and now < self._cached_iam_expires_at - 60:
            return self._cached_iam

        if self._passport_token:
            token, expires_at = self._exchange_passport_token_sync(self._passport_token)
            self._cached_iam = token
            self._cached_iam_expires_at = expires_at
            return token

        if self._iam_token:
            return self._iam_token

        raise RuntimeError("Yandex IAM token unavailable")

    async def _exchange_passport_token(self, passport_token: str) -> tuple[str, float]:
        payload = {"yandexPassportOauthToken": passport_token}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(IAM_TOKEN_URL, json=payload)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Yandex IAM token exchange failed HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )
            data = response.json()

        iam_token = str(data.get("iamToken", "")).strip()
        if not iam_token:
            raise RuntimeError(f"Unexpected IAM token response: {data!r}")

        expires_at = _parse_expires_at(data.get("expiresAt"))
        logger.info("yandex_iam_token_obtained", expires_at=expires_at)
        return iam_token, expires_at

    def _exchange_passport_token_sync(self, passport_token: str) -> tuple[str, float]:
        payload = {"yandexPassportOauthToken": passport_token}
        with httpx.Client(timeout=30.0) as client:
            response = client.post(IAM_TOKEN_URL, json=payload)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Yandex IAM token exchange failed HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )
            data = response.json()

        iam_token = str(data.get("iamToken", "")).strip()
        if not iam_token:
            raise RuntimeError(f"Unexpected IAM token response: {data!r}")

        expires_at = _parse_expires_at(data.get("expiresAt"))
        logger.info("yandex_iam_token_obtained", expires_at=expires_at)
        return iam_token, expires_at


def _parse_expires_at(value: Any) -> float:
    if value is None:
        return time.time() + 3600
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return time.time() + 3600
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.timestamp()
    except ValueError:
        return time.time() + 3600


def build_yandex_auth(cfg: dict[str, Any]) -> YandexAuth:
    return YandexAuth(
        api_key=str(cfg.get("yandex_api_key", "")),
        passport_token=str(cfg.get("yandex_passport_token", "")),
        iam_token=str(cfg.get("yandex_iam_token", "")),
        folder_id=str(cfg.get("yandex_folder_id", "")),
    )

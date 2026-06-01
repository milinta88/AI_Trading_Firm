from __future__ import annotations

import logging
from typing import Any

import requests

from core.models import DeliveryResult

logger = logging.getLogger(__name__)


class TelegramService:
    """Simple Telegram sender for the daily brief."""

    def __init__(
        self,
        bot_token: str | None,
        chat_id: str | None,
        timeout_seconds: int = 10,
        allow_live_sends: bool = False,
        runtime_reason: str = "",
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout_seconds = timeout_seconds
        self.allow_live_sends = allow_live_sends
        self.runtime_reason = runtime_reason

    @property
    def mode_label(self) -> str:
        return "LIVE" if self.allow_live_sends and self.bot_token and self.chat_id else "DRY_RUN"

    def send_message(self, message: str) -> DeliveryResult:
        if not self.allow_live_sends or not self.bot_token or not self.chat_id:
            detail = self.runtime_reason or "Telegram live delivery is unavailable, so the message was logged instead."
            logger.warning("Telegram delivery is running in DRY_RUN mode. %s", detail)
            logger.info("Telegram message preview:\n%s", message)
            return DeliveryResult(
                success=True,
                status="DRY_RUN",
                recipient=self.chat_id or "UNCONFIGURED",
                detail=detail,
            )

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }

        try:
            response = requests.post(url, json=payload, timeout=self.timeout_seconds)
        except requests.Timeout as exc:
            detail = self._sanitize_error_detail(f"Telegram request timed out: {exc}")
            logger.error("Telegram delivery failed with NETWORK_ERROR: %s", detail)
            return DeliveryResult(
                success=False,
                status="NETWORK_ERROR",
                recipient=self.chat_id,
                detail=detail,
            )
        except requests.ConnectionError as exc:
            detail = self._sanitize_error_detail(f"Telegram connection failed: {exc}")
            logger.error("Telegram delivery failed with NETWORK_ERROR: %s", detail)
            return DeliveryResult(
                success=False,
                status="NETWORK_ERROR",
                recipient=self.chat_id,
                detail=detail,
            )
        except requests.RequestException as exc:
            detail = self._sanitize_error_detail(f"Telegram request failed: {exc}")
            logger.error("Telegram delivery failed with REQUEST_ERROR: %s", detail)
            return DeliveryResult(
                success=False,
                status="REQUEST_ERROR",
                recipient=self.chat_id,
                detail=detail,
            )

        response_payload = self._safe_json(response)
        if response.ok and isinstance(response_payload, dict) and response_payload.get("ok"):
            message_id = response_payload.get("result", {}).get("message_id")
            logger.info("Telegram message sent successfully to chat %s.", self._mask_recipient(self.chat_id))
            return DeliveryResult(
                success=True,
                status="SENT",
                recipient=self.chat_id,
                detail="Telegram delivery succeeded.",
                message_id=message_id,
            )

        error_status, error_detail = self._classify_api_error(response, response_payload)
        logger.error("Telegram delivery failed with %s: %s", error_status, error_detail)
        return DeliveryResult(
            success=False,
            status=error_status,
            recipient=self.chat_id,
            detail=error_detail,
        )

    def _classify_api_error(
        self,
        response: requests.Response,
        response_payload: dict[str, Any] | None,
    ) -> tuple[str, str]:
        description = self._extract_api_description(response, response_payload)
        description_lower = description.lower()

        if response.status_code in {401, 404} or "unauthorized" in description_lower:
            status = "INVALID_TOKEN"
        elif response.status_code == 400 and any(
            marker in description_lower
            for marker in ("chat not found", "chat_id", "user not found", "group chat was migrated")
        ):
            status = "INVALID_CHAT_ID"
        elif response.status_code >= 500:
            status = "API_ERROR"
        else:
            status = "API_ERROR"

        return status, self._sanitize_error_detail(description)

    def _extract_api_description(
        self,
        response: requests.Response,
        response_payload: dict[str, Any] | None,
    ) -> str:
        if isinstance(response_payload, dict):
            description = response_payload.get("description")
            if description:
                return str(description)

        response_text = response.text.strip()
        if response_text:
            return response_text[:300]

        return f"Telegram API returned HTTP {response.status_code} without a description."

    @staticmethod
    def _safe_json(response: requests.Response) -> dict[str, Any] | None:
        try:
            payload = response.json()
        except ValueError:
            return None

        return payload if isinstance(payload, dict) else None

    def _sanitize_error_detail(self, detail: str) -> str:
        sanitized = detail
        if self.bot_token:
            sanitized = sanitized.replace(self.bot_token, "[REDACTED_BOT_TOKEN]")
        return sanitized

    @staticmethod
    def _mask_recipient(chat_id: str | None) -> str:
        if not chat_id or len(chat_id) <= 4:
            return chat_id or "UNCONFIGURED"
        return f"...{chat_id[-4:]}"

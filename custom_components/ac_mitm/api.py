"""Async client for the local AC MITM control API."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import CONF_HOST, CONF_PORT, DEFAULT_HOST, DEFAULT_PORT


class AcMitmApiError(Exception):
    """Raised when the MITM control API cannot be reached or refuses."""


class AcMitmApi:
    """Small async wrapper around the MITM HTTP control API."""

    def __init__(self, host: str, port: int, session: aiohttp.ClientSession) -> None:
        self._host = host
        self._port = port
        self._session = session
        self._base = f"http://{host}:{port}"

    @classmethod
    def from_entry(cls, entry, session) -> AcMitmApi:
        data = entry.data if hasattr(entry, "data") else entry
        return cls(
            data.get(CONF_HOST, DEFAULT_HOST),
            int(data.get(CONF_PORT, DEFAULT_PORT)),
            session,
        )

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self._base}{path}"
        try:
            async with asyncio.timeout(10):
                async with self._session.request(method, url, **kwargs) as resp:
                    text = await resp.text()
                    try:
                        data = await resp.json(content_type=None)
                    except Exception:
                        data = {"raw": text}
                    if resp.status >= 400:
                        raise AcMitmApiError(
                            f"{method} {path} -> {resp.status}: {data.get('error', text)[:200]}"
                        )
                    return data
        except AcMitmApiError:
            raise
        except TimeoutError as err:
            raise AcMitmApiError(f"{method} {path} timed out") from err
        except aiohttp.ClientError as err:
            raise AcMitmApiError(f"{method} {path} failed: {err}") from err

    async def async_get_state(self) -> dict[str, Any]:
        """Return the MITM's current view of the AC."""
        return await self._request("GET", "/state")

    async def async_get_messages(self) -> dict[str, Any]:
        """Return captured MQTT messages."""
        return await self._request("GET", "/messages")

    async def async_health(self) -> dict[str, Any]:
        """Return the MITM health payload."""
        return await self._request("GET", "/health")

    async def async_command(
        self,
        action: str,
        value: Any,
        topic: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a high level command to the AC through the MITM."""
        payload: dict[str, Any] = {"action": action, "value": value}
        if topic:
            payload["topic"] = topic
        if extra:
            payload["extra"] = extra
        return await self._request("POST", "/command", json=payload)

    async def async_publish(self, topic: str, payload: dict[str, Any] | str) -> dict[str, Any]:
        """Publish a raw MQTT payload through the MITM."""
        return await self._request("POST", "/publish", json={"topic": topic, "payload": payload})

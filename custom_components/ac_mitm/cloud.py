"""One-time MirAIe account bootstrap. Never used by runtime control."""

from __future__ import annotations

import logging
import asyncio
import uuid
from urllib.parse import quote

import aiohttp

_LOGGER = logging.getLogger(__name__)


class BootstrapError(Exception):
    """The account bootstrap failed without exposing its server response."""


class InvalidAuth(BootstrapError):
    """The account credentials were rejected."""


class Bootstrap:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.token = None
        self.devices: dict[str, dict] = {}

    async def _request(self, method, url, **kwargs):
        host = url.split("/")[2]
    
        try:
            async with asyncio.timeout(20):
                async with self.session.request(
                    method, url, **kwargs
                ) as response:
    
                    if response.status in (401, 403):
                        _LOGGER.warning(
                            "MirAIe %s returned HTTP %s: authentication rejected",
                            host,
                            response.status,
                        )
                        raise InvalidAuth(
                            "MirAIe account authentication was rejected"
                        )
    
                    if response.status >= 400:
                        if response.status == 412:
                            body = await response.text()
                            _LOGGER.warning(
                                "MirAIe %s returned HTTP 412; response body: %r",
                                host,
                                body[:500],
                            )
                        else:
                            _LOGGER.warning(
                                "MirAIe %s returned HTTP %s",
                                host,
                                response.status,
                            )
                    
                        raise BootstrapError("MirAIe bootstrap request failed")
    
                    return await response.json(content_type=None)
    
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            _LOGGER.warning(
                "MirAIe request to %s failed: %s",
                host,
                type(err).__name__,
            )
            raise BootstrapError(
                "Cannot reach MirAIe account service"
            ) from err

    async def login(self, username: str, password: str) -> dict[str, str]:
        payload = {
            "clientId": "292d99d7-5623-4157-8a71-846ee3ff5dbf",
            "password": password,
            "scope": "an_" + uuid.uuid4().hex,
        }
        payload["email" if "@" in username else "mobile"] = username.strip()
        response = await self._request(
            "POST", "https://auth.miraie.in/simplifi/v1/userManagement/login", json=payload
        )
        self.token = response.get("accessToken")
        if not self.token:
            raise InvalidAuth("MirAIe account authentication was rejected")
        homes = await self._get("homeManagement/homes")
        if not isinstance(homes, list):
            raise BootstrapError("Unexpected account device response")
        self.devices = {}
        for home in homes:
            for space in home.get("spaces", []):
                for device in space.get("devices", []):
                    if (
                        isinstance(device, dict)
                        and device.get("deviceId")
                        and device.get("category", "AC").upper() == "AC"
                    ):
                        self.devices[device["deviceId"]] = {**device, "home": home}
        return {
            key: str(
                device.get("deviceName")
                or device.get("name")
                or device.get("modelName")
                or "Panasonic AC"
            )
            for key, device in self.devices.items()
        }

    async def _get(self, path):
        return await self._request(
            "GET",
            "https://app.miraie.in/simplifi/v1/" + path,
            headers={"Authorization": "Bearer " + self.token},
        )

    async def credentials(self, device_id: str) -> dict:
        registered = self.devices[device_id]
        response = await self._get("deviceManagement/devices/deviceId/" + quote(device_id, safe=""))
        if isinstance(response, list):
            response = next((d for d in response if d.get("deviceId") == device_id), {})
        if not isinstance(response, dict):
            raise BootstrapError("Unexpected device response")
        # Some firmware/account versions return home-level keys instead.
        home = registered["home"]
        key = response.get("udpControlKey") or home.get("udpControlKey")
        iv = response.get("udpControlIV") or home.get("udpControlIV")
        if not key or not iv:
            raise BootstrapError("This device does not expose a native local control key")
        result = {
            "device_id": device_id,
            "mac": response.get("macAddress", ""),
            "key": key,
            "iv": iv,
            "model": response.get("modelNumber"),
            "firmware": response.get("firmwareVersion"),
            "name": registered.get("deviceName")
            or registered.get("name")
            or "Panasonic AC (Local)",
        }
        # Do not keep password, account identifiers, tokens, Matter codes or cloud response.
        self.token = None
        self.devices = {}
        return result

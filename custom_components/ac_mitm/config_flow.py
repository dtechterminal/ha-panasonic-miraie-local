"""Obtain local keys once, verify native control, then explain WAN blocking."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AcMitmApi, AcMitmApiError
from .cloud import Bootstrap, BootstrapError, InvalidAuth
from .const import DOMAIN
from .native import NativeApi, verify_local
from .transport import UdpTransport, discover_host, local_config


class AcMitmConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def __init__(self):
        self._bootstrap = None
        self._devices = {}
        self._config: dict[str, Any] = {}
        self._discovery_task = None

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["account", "manual", "bridge"])

    async def async_step_reconfigure(self, user_input=None) -> ConfigFlowResult:
        self._config = local_config(dict(self._get_reconfigure_entry().data))
        if self._config.get("device_id"):
            return await self.async_step_network()
        return await self.async_step_user()

    def _finish(self, title, data):
        if self.source == "reconfigure":
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                data=data,
                title=title,
                unique_id=data.get("device_id") or self.unique_id,
            )
        return self.async_create_entry(title=title, data=data)

    async def _check_device_unique_id(self):
        await self.async_set_unique_id(self._config["device_id"])
        if (
            self.source == "reconfigure"
            and self._get_reconfigure_entry().unique_id == self._config["device_id"]
        ):
            return
        self._abort_if_unique_id_configured()

    async def async_step_account(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            self._bootstrap = Bootstrap(async_get_clientsession(self.hass))
            try:
                self._devices = await self._bootstrap.login(
                    user_input["username"], user_input["password"]
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except BootstrapError:
                errors["base"] = "cannot_connect"
            else:
                if not self._devices:
                    errors["base"] = "no_devices"
                elif len(self._devices) == 1:
                    return await self.async_step_device({"device_id": next(iter(self._devices))})
                else:
                    return await self.async_step_device()
        return self.async_show_form(
            step_id="account",
            data_schema=vol.Schema(
                {
                    vol.Required("username"): str,
                    vol.Required("password"): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_device(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                self._config.update(await self._bootstrap.credentials(user_input["device_id"]))
            except BootstrapError:
                errors["base"] = "no_local_key"
            else:
                self._bootstrap = None
                await self._check_device_unique_id()
                return await self.async_step_discover()
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required("device_id"): vol.In(
                        {k: f"{v} ({k[-4:]})" for k, v in self._devices.items()}
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_manual(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            from .protocol import Protocol, ProtocolError

            try:
                Protocol(user_input["device_id"], user_input["key"], user_input["iv"])
            except (ValueError, ProtocolError):
                errors["base"] = "invalid_key"
            else:
                self._config.update(user_input)
                await self._check_device_unique_id()
                return await self.async_step_network()
        secret = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        )
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required("device_id"): str,
                    vol.Required("key"): secret,
                    vol.Required("iv"): secret,
                }
            ),
            errors=errors,
        )

    async def _discover_and_verify(self):
        if self._config.get("host"):
            return await self._verify()
        shared = self.hass.data.setdefault(DOMAIN, {})
        lock = shared.setdefault("_udp_lock", asyncio.Lock())
        try:
            host = await discover_host(self._config, lock)
        except (OSError, ValueError):
            return False
        if not host:
            return False
        self._config.update({"host": host, "transport": "auto"})
        return await self._verify()

    async def async_step_discover(self, user_input=None) -> ConfigFlowResult:
        if self._discovery_task is None:
            self._discovery_task = self.hass.async_create_task(self._discover_and_verify())
        if not self._discovery_task.done():
            return self.async_show_progress(
                step_id="discover",
                progress_action="local_setup",
                progress_task=self._discovery_task,
            )
        success = self._discovery_task.result()
        self._discovery_task = None
        return self.async_show_progress_done(next_step_id="firewall" if success else "network")

    async def async_step_network(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            self._config = local_config(self._config)
            if self.show_advanced_options:
                for optional in ("packet_interface", "vlan_id"):
                    self._config.pop(optional, None)
            self._config.update(user_input)
            if await self._verify():
                return await self.async_step_firewall()
            errors["base"] = "local_unreachable"
        schema = {
            vol.Required("host", default=self._config.get("host", "")): str,
            vol.Required("transport", default=self._config.get("transport", "auto")): vol.In(
                {
                    "auto": "Automatic (recommended)",
                    "direct": "Standard UDP",
                    "packet": "HA-local VLAN receiver (Linux)",
                }
            ),
        }
        if self.show_advanced_options:
            for key, validator in (
                ("packet_interface", str),
                ("vlan_id", vol.All(vol.Coerce(int), vol.Range(min=1, max=4094))),
            ):
                default = {"default": self._config[key]} if key in self._config else {}
                schema[vol.Optional(key, **default)] = validator
        return self.async_show_form(
            step_id="network", data_schema=vol.Schema(schema), errors=errors
        )

    async def _verify(self):
        try:
            shared = self.hass.data.setdefault(DOMAIN, {})
            lock = shared.setdefault("_udp_lock", asyncio.Lock())
            api = NativeApi(self._config, UdpTransport(self._config, lock))
            await verify_local(api)
            return True
        except (AcMitmApiError, OSError, ValueError, KeyError):
            return False

    async def async_step_firewall(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            if not await self._verify():
                return self.async_show_form(
                    step_id="firewall",
                    data_schema=vol.Schema({}),
                    errors={"base": "local_unreachable"},
                )
            return self._finish(
                title=self._config.get("name") or "Panasonic AC (Local)",
                data={**self._config, "local_verified": True},
            )
        return self.async_show_form(step_id="firewall", data_schema=vol.Schema({}))

    async def async_step_bridge(self, user_input=None) -> ConfigFlowResult:
        """Compatibility for existing external HTTP bridges."""
        errors = {}
        if user_input is not None:
            try:
                api = AcMitmApi(
                    user_input["host"], user_input["port"], async_get_clientsession(self.hass)
                )
                state = await api.async_get_state()
                if (
                    not state.get("local", {}).get("available")
                    or state.get("ac", {}).get("_transport") != "local_udp"
                ):
                    raise AcMitmApiError("Bridge native local control is not available")
            except AcMitmApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{user_input['host']}:{user_input['port']}")
                self._abort_if_unique_id_configured()
                return self._finish(
                    title="Panasonic AC (Local Bridge)", data={**user_input, "transport": "bridge"}
                )
        return self.async_show_form(
            step_id="bridge",
            data_schema=vol.Schema(
                {
                    vol.Required("host"): str,
                    vol.Required("port", default=8090): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                }
            ),
            errors=errors,
        )

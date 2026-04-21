"""The Nature Remo integration."""

import logging
from datetime import timedelta
from typing import Any, Dict

import voluptuous as vol
from aiohttp import ClientSession
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from propcache.api import cached_property

_LOGGER = logging.getLogger(__name__)
_RESOURCE = "https://api.nature.global/1/"

DOMAIN = "nature_remo"

CONF_COOL_TEMP = "cool_temperature"
CONF_HEAT_TEMP = "heat_temperature"
DEFAULT_COOL_TEMP = 28
DEFAULT_HEAT_TEMP = 20
DEFAULT_UPDATE_INTERVAL = timedelta(seconds=60)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_ACCESS_TOKEN): cv.string,
                vol.Optional(CONF_COOL_TEMP, default=DEFAULT_COOL_TEMP): vol.Coerce(int),
                vol.Optional(CONF_HEAT_TEMP, default=DEFAULT_HEAT_TEMP): vol.Coerce(int),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Nature Remo component."""
    _LOGGER.debug("Setting up Nature Remo component.")
    access_token = config[DOMAIN][CONF_ACCESS_TOKEN]
    session = async_get_clientsession(hass)
    api = NatureRemoAPI(access_token, session)
    coordinator = hass.data[DOMAIN] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Nature Remo update",
        update_method=api.get,
        update_interval=DEFAULT_UPDATE_INTERVAL,
    )
    await coordinator.async_refresh()
    hass.data[DOMAIN] = {
        "api": api,
        "coordinator": coordinator,
        "config": config[DOMAIN],
    }

    await discovery.async_load_platform(hass, "sensor", DOMAIN, {}, config)
    await discovery.async_load_platform(hass, "climate", DOMAIN, {}, config)
    await discovery.async_load_platform(hass, "light", DOMAIN, {}, config)
    return True


class NatureRemoAPI:
    """Nature Remo API client"""

    def __init__(self, access_token: str, session: ClientSession) -> None:
        """Init API client"""
        self._access_token = access_token
        self._session = session

    async def get(self) -> Dict[str, Dict[str, Any]]:
        """Get appliance and device list"""
        _LOGGER.debug("Trying to fetch appliance and device list from API.")
        headers = {"Authorization": f"Bearer {self._access_token}"}
        response = await self._session.get(f"{_RESOURCE}/appliances", headers=headers)
        appliances = {x["id"]: x for x in await response.json()}
        response = await self._session.get(f"{_RESOURCE}/devices", headers=headers)
        devices = {x["id"]: x for x in await response.json()}
        return {"appliances": appliances, "devices": devices}

    async def post(self, path: str, data: Dict[str, Any]) -> Any:
        """Post any request"""
        _LOGGER.debug("Trying to request post:%s, data:%s", path, data)
        headers = {"Authorization": f"Bearer {self._access_token}"}
        response = await self._session.post(f"{_RESOURCE}{path}", data=data, headers=headers)
        return await response.json()


class NatureRemoBase(Entity):
    """Nature Remo entity base class."""

    def __init__(self, coordinator: DataUpdateCoordinator, appliance: Dict[str, Any]) -> None:
        self._coordinator = coordinator
        self._name = f"Nature Remo {appliance['nickname']}"
        self._appliance_id = appliance["id"]
        self._device = appliance["device"]

    @cached_property
    def name(self) -> str | None:
        """Return the name of the sensor."""
        return self._name

    @cached_property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._appliance_id

    @cached_property
    def should_poll(self) -> bool:
        """Return the polling requirement of the entity."""
        return False

    @cached_property
    def device_info(self) -> DeviceInfo | None:
        """Return the device info for the sensor."""
        # Since device registration requires Config Entries, this dosen't work for now
        return {
            "identifiers": {(DOMAIN, self._device["id"])},
            "name": self._device["name"] or "Unknown Device",
            "manufacturer": "Nature Remo",
            "model": self._device.get("serial_number") or "Unknown Model",
            "sw_version": self._device.get("firmware_version") or "Unknown Version",
        }


class NatureRemoDeviceBase(Entity):
    """Nature Remo Device entity base class."""

    def __init__(self, coordinator: DataUpdateCoordinator, device: Dict[str, Any]) -> None:
        self._coordinator = coordinator
        self._name = f"Nature Remo {device['name']}"
        self._device = device

    @cached_property
    def name(self) -> str | None:
        """Return the name of the sensor."""
        return self._name

    @cached_property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._device["id"]

    @cached_property
    def should_poll(self) -> bool:
        """Return the polling requirement of the entity."""
        return True

    @cached_property
    def device_info(self) -> DeviceInfo | None:
        """Return the device info for the sensor."""
        # Since device registration requires Config Entries, this dosen't work for now
        return {
            "identifiers": {(DOMAIN, self._device["id"])},
            "name": self._device["name"] or "Unknown Device",
            "manufacturer": "Nature Remo",
            "model": self._device.get("serial_number") or "Unknown Model",
            "sw_version": self._device.get("firmware_version") or "Unknown Version",
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        self.async_on_remove(self._coordinator.async_add_listener(self.async_write_ha_state))

    async def async_update(self) -> None:
        """Update the entity.
        Only used by the generic entity update service.
        """
        await self._coordinator.async_request_refresh()

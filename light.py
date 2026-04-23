"""Support for Nature Remo Light."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional

import voluptuous as vol
from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import DOMAIN, NatureRemoAPI, NatureRemoBase

_LOGGER = logging.getLogger(__name__)

SERVICE_PRESS_LIGHT_BUTTON = "press_light_button"
SERVICE_PRESS_CUSTOM_BUTTON = "press_custom_button"

ATTR_IS_NIGHT = "is_night"


class LightButton(Enum):
    on = "on"
    max = "on-100"
    favorite = "on-favorite"
    on_off = "onoff"
    night = "night"
    bright_up = "bright-up"
    bright_down = "bright-down"
    color_temp_up = "colortemp-up"
    color_temp_down = "colortemp-down"


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the Nature Remo Light."""
    if discovery_info is None:
        return

    _LOGGER.debug("Setting up light platform.")

    coordinator: DataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]
    api: NatureRemoAPI = hass.data[DOMAIN]["api"]
    appliances = coordinator.data["appliances"]

    entities = [
        NatureRemoLight(coordinator, api, appliance)
        for appliance in appliances.values()
        if appliance.get("type") == "LIGHT"
    ]
    async_add_entities(entities)

    platform = entity_platform.async_get_current_platform()

    _LOGGER.debug("Registering light entity services.")
    platform.async_register_entity_service(
        SERVICE_PRESS_LIGHT_BUTTON,
        {vol.Required("button_name"): cv.enum(LightButton)},
        "async_press_light_button",
    )
    platform.async_register_entity_service(
        SERVICE_PRESS_CUSTOM_BUTTON,
        {vol.Required("button_name"): cv.string},
        "async_press_custom_button",
    )


class NatureRemoLight(NatureRemoBase, LightEntity):
    """Representation of a Nature Remo light appliance."""

    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF
    _attr_assumed_state = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: NatureRemoAPI,
        appliance: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, appliance)
        self._api = api
        self._signals: dict[str, str] = {}
        self._is_on = False
        self._is_night = False
        self._update_from_appliance(appliance)

    @property
    def is_on(self) -> bool:
        """Return True if the light is on."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self._coordinator.last_update_success:
            return False
        return self._appliance_id in self._coordinator.data.get("appliances", {})

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if not self.is_on:
            return None
        return {ATTR_IS_NIGHT: self._is_night}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        await self._post_light({"button": LightButton.on.value})
        self._set_state(is_on=True, is_night=False)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._post_light({"button": "off"})
        self._set_state(is_on=False, is_night=False)

    async def async_press_light_button(self, button_name: LightButton) -> None:
        """Press one of the built-in Remo light buttons."""
        await self._post_light({"button": button_name.value})

        if button_name == LightButton.on_off:
            self._set_state(is_on=not self._is_on, is_night=False)
            return

        if button_name == LightButton.night:
            if self._is_on and self._is_night:
                self._set_state(is_on=False, is_night=False)
            else:
                self._set_state(is_on=True, is_night=True)
            return

        self._set_state(is_on=True, is_night=False)

    async def async_press_custom_button(self, button_name: str) -> None:
        """Press a custom button registered as a signal in the Remo app."""
        signal_id = self._signals.get(button_name)
        if signal_id is None:
            _LOGGER.error("Invalid signal name: %s", button_name)
            return

        await self._api.post(f"/signals/{signal_id}/send", {})
        self._set_state(is_on=True, is_night=False)

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates."""
        self.async_on_remove(self._coordinator.async_add_listener(self._update_callback))

    @callback
    def _update_callback(self) -> None:
        appliance = self._coordinator.data.get("appliances", {}).get(self._appliance_id)
        if appliance is not None:
            self._update_from_appliance(appliance)
        self.async_write_ha_state()

    def _update_from_appliance(self, appliance: dict[str, Any]) -> None:
        self._signals = {s["name"]: s["id"] for s in appliance.get("signals", []) if "id" in s and "name" in s}

    async def _post_light(self, data: dict[str, Any]) -> None:
        await self._api.post(f"/appliances/{self._appliance_id}/light", data)

    def _set_state(self, is_on: bool, is_night: bool) -> None:
        self._is_on = is_on
        self._is_night = is_night
        self.async_write_ha_state()

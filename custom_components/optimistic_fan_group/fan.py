"""Fan platform for the Optimistic Fan Group integration.

The group entity is fully autonomous: it never reads the state of its member
fans (zero feedback). Every user command is forwarded to the members and
immediately persisted in the group's own optimistic cache — including across
Home Assistant restarts — without any confirmation from the network or the
devices.
"""

from __future__ import annotations

import hashlib
import logging
import voluptuous as vol

from homeassistant.components.fan import (
    DOMAIN as FAN_DOMAIN,
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
    FanEntity,
    FanEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_NAME,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import slugify

from .const import (
    ATTR_DIRECTION,
    ATTR_OSCILLATING,
    ATTR_PERCENTAGE,
    CONF_FANS,
    DEFAULT_NAME,
    DOMAIN,
    SERVICE_SYNC,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_TURN_ON = "turn_on"
SERVICE_TURN_OFF = "turn_off"
SERVICE_SET_PERCENTAGE = "set_percentage"
SERVICE_SET_DIRECTION = "set_direction"
SERVICE_OSCILLATE = "oscillate"

SUPPORTED_FEATURES = (
    FanEntityFeature.TURN_ON
    | FanEntityFeature.TURN_OFF
    | FanEntityFeature.SET_SPEED
    | FanEntityFeature.DIRECTION
    | FanEntityFeature.OSCILLATE
)

PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_FANS): cv.entity_ids,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the group from a config entry."""
    _async_register_sync_service(hass)

    fans: list[str] = list(entry.options.get(CONF_FANS, entry.data.get(CONF_FANS, [])))
    if not fans:
        _LOGGER.warning(
            "Optimistic Fan Group '%s' has no member fan configured", entry.title
        )
        return

    async_add_entities(
        [
            OptimisticFanGroup(
                hass=hass,
                unique_id=entry.entry_id,
                name=entry.title,
                entity_ids=fans,
            )
        ]
    )


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the group from the legacy YAML configuration."""
    _async_register_sync_service(hass)

    name: str = config[CONF_NAME]
    entity_ids: list[str] = config[CONF_FANS]

    unique_id = f"{DOMAIN}_{slugify(name)}_{hashlib.sha1(','.join(entity_ids).encode()).hexdigest()[:8]}"

    entity = OptimisticFanGroup(
        hass=hass,
        unique_id=unique_id,
        name=name,
        entity_ids=entity_ids,
    )
    entity.entity_id = f"{FAN_DOMAIN}.{slugify(name)}"

    async_add_entities([entity])


@callback
def _async_register_sync_service(hass: HomeAssistant) -> None:
    """Register the <domain>.sync entity service exactly once."""
    if hass.services.has_service(DOMAIN, SERVICE_SYNC):
        return
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SYNC,
        None,
        "async_sync",
    )


class OptimisticFanGroup(FanEntity, RestoreEntity):
    """A fan group fully autonomous from its members (zero feedback).

    The group state only ever reflects the commands issued on the group
    itself; the members' states are never read automatically.
    """

    _attr_should_poll = False
    _attr_has_entity_name = False
    _attr_supported_features = SUPPORTED_FEATURES
    _attr_assumed_state = True

    def __init__(
        self,
        hass: HomeAssistant,
        unique_id: str,
        name: str,
        entity_ids: list[str],
    ) -> bool:
        """Initialize the group."""
        self.hass = hass
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._entity_ids = entity_ids

        # Optimistic cache: defaults to off until the first command.
        self._attr_is_on: bool = False
        self._attr_percentage: int | None = None
        self._attr_current_direction: str | None = None
        self._attr_oscillating: bool | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last commanded state — never read the members' state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        self._attr_is_on = last_state.state == STATE_ON
        percentage = last_state.attributes.get(ATTR_PERCENTAGE)
        if percentage is not None:
            self._attr_percentage = int(percentage)
        self._attr_current_direction = last_state.attributes.get(ATTR_DIRECTION)
        self._attr_oscillating = last_state.attributes.get(ATTR_OSCILLATING)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    @property
    def is_on(self) -> bool | None:
        """Return the optimistic on/off state, independent of percentage."""
        return self._attr_is_on

    @property
    def extra_state_attributes(self) -> dict:
        """Return the member entities of the group."""
        return {"members": self._entity_ids}

    # ------------------------------------------------------------------
    # Commands (optimistic: cache first, then forward to the members)
    # ------------------------------------------------------------------
    async def _forward(self, service: str, data: dict) -> None:
        """Forward a fan service call to every member of the group."""
        data = {ATTR_ENTITY_ID: self._entity_ids, **data}
        try:
            await self.hass.services.async_call(
                FAN_DOMAIN,
                service,
                data,
                blocking=True,
                context=self._context,
            )
        except Exception:  # noqa: BLE001 - the optimistic state must not break
            _LOGGER.exception(
                "Failed to forward fan.%s to %s", service, self._entity_ids
            )

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs,
    ) -> None:
        """Turn the group on immediately, forward to every member."""
        if percentage is not None:
            self._attr_percentage = percentage
        elif self._attr_percentage is None:
            self._attr_percentage = 100
        self._attr_is_on = True
        self.async_write_ha_state()

        # Forward the cached speed too, so members match the group exactly.
        await self._forward(SERVICE_TURN_ON, {ATTR_PERCENTAGE: self._attr_percentage})

    async def async_turn_off(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs,
    ) -> None:
        """Turn the group off immediately, forward to every member."""
        # Keep the cached percentage so turning back on restores it.
        self._attr_is_on = False
        self.async_write_ha_state()

        await self._forward(SERVICE_TURN_OFF, {})

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed, turning the group on if it was off."""
        if percentage == 0:
            # Speed 0 means off: keep the last non-zero speed for the next
            # turn-on so it stays persistent.
            self._attr_is_on = False
            self.async_write_ha_state()
            await self._forward(SERVICE_TURN_OFF, {})
            return

        was_on = self._attr_is_on
        self._attr_percentage = percentage
        self._attr_is_on = True
        self.async_write_ha_state()

        if was_on:
            await self._forward(SERVICE_SET_PERCENTAGE, {ATTR_PERCENTAGE: percentage})
        else:
            # Group was off: turn the members on with the requested speed.
            await self._forward(SERVICE_TURN_ON, {ATTR_PERCENTAGE: percentage})

    async def async_set_direction(self, direction: str) -> None:
        """Set the direction of every member and of the optimistic cache."""
        if direction not in (DIRECTION_FORWARD, DIRECTION_REVERSE):
            _LOGGER.warning("Unsupported direction: %s", direction)
            return

        self._attr_current_direction = direction
        self.async_write_ha_state()

        await self._forward(SERVICE_SET_DIRECTION, {ATTR_DIRECTION: direction})

    async def async_oscillate(self, oscillating: bool) -> None:
        """Set oscillation of every member and of the optimistic cache."""
        self._attr_oscillating = oscillating
        self.async_write_ha_state()

        await self._forward(SERVICE_OSCILLATE, {ATTR_OSCILLATING: oscillating})

    async def async_sync(self) -> None:
        """Discard the optimistic cache and reload the real member state."""
        self._apply_real_state(warn=True)

    @callback
    def _apply_real_state(self, warn: bool = True) -> None:
        """Copy the real state of the member fans into the cache."""
        best_state = None
        for entity_id in self._entity_ids:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            if state.state == "on":
                best_state = state
                break
            if best_state is None:
                best_state = state

        if best_state is None:
            if warn:
                _LOGGER.warning("No member fan available to synchronize with")
            return

        self._attr_is_on = best_state.state == "on"
        self._attr_percentage = best_state.attributes.get(ATTR_PERCENTAGE)
        self._attr_current_direction = best_state.attributes.get(ATTR_DIRECTION)
        self._attr_oscillating = best_state.attributes.get(ATTR_OSCILLATING)
        self.async_write_ha_state()

"""Smoke tests for the optimistic_fan_group integration."""

import pytest

from homeassistant.components import fan
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.optimistic_fan_group.const import CONF_FANS, DOMAIN

MEMBERS = ["fan.member_one", "fan.member_two"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of custom integrations."""
    yield


async def _setup_group(hass: HomeAssistant) -> MockConfigEntry:
    """Create two member fan states and set up the group entry."""
    for entity_id in MEMBERS:
        hass.states.async_set(
            entity_id,
            "on",
            {
                fan.ATTR_PERCENTAGE: 50,
                fan.ATTR_DIRECTION: fan.DIRECTION_FORWARD,
                fan.ATTR_OSCILLATING: False,
            },
        )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Group",
        data={"name": "Test Group", CONF_FANS: MEMBERS},
        unique_id="test_group",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_group_entity_created(hass: HomeAssistant) -> None:
    """The group entity exists and exposes its members."""
    await _setup_group(hass)

    state = hass.states.get("fan.test_group")
    assert state is not None
    assert state.state == "on"
    assert state.attributes[fan.ATTR_PERCENTAGE] == 50
    assert state.attributes["members"] == MEMBERS
    assert state.attributes["assumed_state"] is True


async def test_turn_off_is_optimistic(hass: HomeAssistant) -> None:
    """Turning the group off flips its state without touching members."""
    await _setup_group(hass)

    await hass.services.async_call(
        fan.DOMAIN,
        "turn_off",
        {"entity_id": "fan.test_group"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get("fan.test_group").state == "off"
    # Members were only simulated entities, their state never changed.
    assert hass.states.get("fan.member_one").state == "on"


async def test_set_percentage_updates_cache(hass: HomeAssistant) -> None:
    """Setting the speed updates the optimistic percentage immediately."""
    await _setup_group(hass)

    await hass.services.async_call(
        fan.DOMAIN,
        "set_percentage",
        {"entity_id": "fan.test_group", fan.ATTR_PERCENTAGE: 75},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get("fan.test_group")
    assert state.attributes[fan.ATTR_PERCENTAGE] == 75
    assert state.state == "on"


async def test_turn_on_after_off_restores_percentage(hass: HomeAssistant) -> None:
    """Turn on again after off keeps the cached percentage."""
    await _setup_group(hass)

    await hass.services.async_call(
        fan.DOMAIN,
        "turn_off",
        {"entity_id": "fan.test_group"},
        blocking=True,
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        fan.DOMAIN,
        "turn_on",
        {"entity_id": "fan.test_group"},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get("fan.test_group")
    assert state.state == "on"
    assert state.attributes[fan.ATTR_PERCENTAGE] == 50


async def test_sync_service_reloads_real_state(hass: HomeAssistant) -> None:
    """The sync service discards the cache and reads the members again."""
    await _setup_group(hass)

    hass.states.async_set("fan.member_one", "off", {fan.ATTR_PERCENTAGE: 25})
    hass.states.async_set("fan.member_two", "off", {fan.ATTR_PERCENTAGE: 25})

    await hass.services.async_call(
        DOMAIN,
        "sync",
        {"entity_id": "fan.test_group"},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get("fan.test_group")
    assert state.state == "off"
    assert state.attributes[fan.ATTR_PERCENTAGE] == 25


async def test_direction_and_oscillation(hass: HomeAssistant) -> None:
    """Direction and oscillation commands are cached optimistically."""
    await _setup_group(hass)

    await hass.services.async_call(
        fan.DOMAIN,
        "set_direction",
        {"entity_id": "fan.test_group", fan.ATTR_DIRECTION: fan.DIRECTION_REVERSE},
        blocking=True,
    )
    await hass.services.async_call(
        fan.DOMAIN,
        "oscillate",
        {"entity_id": "fan.test_group", fan.ATTR_OSCILLATING: True},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get("fan.test_group")
    assert state.attributes[fan.ATTR_DIRECTION] == fan.DIRECTION_REVERSE
    assert state.attributes[fan.ATTR_OSCILLATING] is True


async def test_yaml_platform_setup(hass: HomeAssistant) -> None:
    """The legacy YAML platform setup works as a fallback."""
    from homeassistant.setup import async_setup_component

    for entity_id in MEMBERS:
        hass.states.async_set(entity_id, "on", {fan.ATTR_PERCENTAGE: 40})

    assert await async_setup_component(
        hass,
        fan.DOMAIN,
        {
            fan.DOMAIN: {
                "platform": "optimistic_fan_group",
                "name": "Yaml Group",
                "fans": MEMBERS,
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("fan.yaml_group")
    assert state is not None
    assert state.state == "on"
    assert state.attributes[fan.ATTR_PERCENTAGE] == 40

    await hass.services.async_call(
        fan.DOMAIN,
        "turn_off",
        {"entity_id": "fan.yaml_group"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get("fan.yaml_group").state == "off"


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    """The config flow creates an entry with name + members."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Living Room Fans", "fans": MEMBERS},
    )
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert result["title"] == "Living Room Fans"
    assert result["data"]["fans"] == MEMBERS

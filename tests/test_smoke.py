"""Tests for the optimistic_fan_group integration."""

from unittest.mock import patch

import pytest

from homeassistant.components import fan
from homeassistant.core import HomeAssistant, State

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

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


async def _group_service(hass: HomeAssistant, service: str, data: dict) -> None:
    """Call a fan service on the group entity."""
    await hass.services.async_call(
        fan.DOMAIN,
        service,
        {"entity_id": "fan.test_group", **data},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_group_entity_created(hass: HomeAssistant) -> None:
    """The group exists but never seeds its state from the members."""
    await _setup_group(hass)

    state = hass.states.get("fan.test_group")
    assert state is not None
    # Zero feedback: members report on/50% but a fresh group starts off.
    assert state.state == "off"
    assert state.attributes.get(fan.ATTR_PERCENTAGE) is None
    assert state.attributes["members"] == MEMBERS
    assert state.attributes["assumed_state"] is True
    assert state.state != "unavailable"


async def test_turn_off_is_optimistic(hass: HomeAssistant) -> None:
    """Turning the group off flips its state without touching members."""
    await _setup_group(hass)

    await _group_service(hass, "turn_on", {})
    assert hass.states.get("fan.test_group").state == "on"

    await _group_service(hass, "turn_off", {})
    assert hass.states.get("fan.test_group").state == "off"
    # Members were only simulated entities, their state never changed.
    assert hass.states.get("fan.member_one").state == "on"


async def test_set_percentage_while_off_turns_group_on(hass: HomeAssistant) -> None:
    """Setting a speed on an off group turns it on and persists the speed."""
    await _setup_group(hass)
    assert hass.states.get("fan.test_group").state == "off"

    await _group_service(hass, "set_percentage", {fan.ATTR_PERCENTAGE: 40})

    state = hass.states.get("fan.test_group")
    assert state.state == "on"
    assert state.attributes[fan.ATTR_PERCENTAGE] == 40


async def test_member_state_changes_never_affect_group(hass: HomeAssistant) -> None:
    """The group ignores every state report from its members."""
    await _setup_group(hass)
    await _group_service(hass, "set_percentage", {fan.ATTR_PERCENTAGE: 60})
    assert hass.states.get("fan.test_group").state == "on"

    # Members now report off / 0% / unavailable — the group must not care.
    hass.states.async_set("fan.member_one", "off", {fan.ATTR_PERCENTAGE: 0})
    hass.states.async_set("fan.member_two", "unavailable")
    await hass.async_block_till_done()

    state = hass.states.get("fan.test_group")
    assert state.state == "on"
    assert state.attributes[fan.ATTR_PERCENTAGE] == 60
    assert state.state != "unavailable"


async def test_turn_on_after_off_restores_percentage(hass: HomeAssistant) -> None:
    """Turn on again after off keeps the cached percentage."""
    await _setup_group(hass)

    await _group_service(hass, "set_percentage", {fan.ATTR_PERCENTAGE: 50})
    await _group_service(hass, "turn_off", {})
    await _group_service(hass, "turn_on", {})

    state = hass.states.get("fan.test_group")
    assert state.state == "on"
    assert state.attributes[fan.ATTR_PERCENTAGE] == 50


async def test_speed_zero_turns_off_but_speed_persists(hass: HomeAssistant) -> None:
    """Speed 0 turns the group off without erasing the stored speed."""
    await _setup_group(hass)

    await _group_service(hass, "set_percentage", {fan.ATTR_PERCENTAGE: 60})
    await _group_service(hass, "set_percentage", {fan.ATTR_PERCENTAGE: 0})

    state = hass.states.get("fan.test_group")
    assert state.state == "off"
    assert state.attributes[fan.ATTR_PERCENTAGE] == 60

    await _group_service(hass, "turn_on", {})
    state = hass.states.get("fan.test_group")
    assert state.state == "on"
    assert state.attributes[fan.ATTR_PERCENTAGE] == 60


async def test_commands_are_forwarded_to_members(hass: HomeAssistant) -> None:
    """Commands are forwarded to the members with the right service."""
    await _setup_group(hass)

    calls: list[tuple[str, str, dict]] = []
    service_cls = type(hass.services)
    original = service_cls.async_call

    async def spy(self, domain, service, service_data, *args, **kwargs):
        calls.append((domain, service, dict(service_data)))
        return await original(self, domain, service, service_data, *args, **kwargs)

    with patch.object(service_cls, "async_call", new=spy):
        # Off + speed -> members must receive turn_on WITH the requested speed.
        await _group_service(hass, "set_percentage", {fan.ATTR_PERCENTAGE: 40})
        # On -> subsequent speed change uses set_percentage.
        await _group_service(hass, "set_percentage", {fan.ATTR_PERCENTAGE: 55})
        await _group_service(hass, "turn_off", {})

    member_calls = [
        (dom, svc, data) for dom, svc, data in calls if data.get("entity_id") == MEMBERS
    ]
    assert (
        fan.DOMAIN,
        "turn_on",
        {"entity_id": MEMBERS, fan.ATTR_PERCENTAGE: 40},
    ) in member_calls
    assert (
        fan.DOMAIN,
        "set_percentage",
        {"entity_id": MEMBERS, fan.ATTR_PERCENTAGE: 55},
    ) in member_calls
    assert (fan.DOMAIN, "turn_off", {"entity_id": MEMBERS}) in member_calls


async def test_sync_service_reloads_real_state(hass: HomeAssistant) -> None:
    """The sync service (manual, opt-in) discards the cache and reads members."""
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

    await _group_service(
        hass, "set_direction", {fan.ATTR_DIRECTION: fan.DIRECTION_REVERSE}
    )
    await _group_service(hass, "oscillate", {fan.ATTR_OSCILLATING: True})

    state = hass.states.get("fan.test_group")
    assert state.attributes[fan.ATTR_DIRECTION] == fan.DIRECTION_REVERSE
    assert state.attributes[fan.ATTR_OSCILLATING] is True


async def test_state_restored_after_restart(hass: HomeAssistant) -> None:
    """The last commanded state survives a Home Assistant restart."""
    mock_restore_cache(
        hass,
        [
            State(
                "fan.test_group",
                "on",
                {
                    fan.ATTR_PERCENTAGE: 30,
                    fan.ATTR_DIRECTION: fan.DIRECTION_REVERSE,
                    fan.ATTR_OSCILLATING: True,
                },
            )
        ],
    )
    await _setup_group(hass)

    state = hass.states.get("fan.test_group")
    assert state.state == "on"
    assert state.attributes[fan.ATTR_PERCENTAGE] == 30
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

    # Zero feedback: the YAML group starts off despite members on at 40%.
    state = hass.states.get("fan.yaml_group")
    assert state is not None
    assert state.state == "off"
    assert state.attributes["members"] == MEMBERS

    await hass.services.async_call(
        fan.DOMAIN,
        "set_percentage",
        {"entity_id": "fan.yaml_group", fan.ATTR_PERCENTAGE: 40},
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get("fan.yaml_group")
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

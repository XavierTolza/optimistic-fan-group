"""Config and options flows for the Optimistic Fan Group integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components import fan
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
)

from .const import CONF_FANS, DEFAULT_NAME, DOMAIN


class OptimisticFanGroupConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Ask for the group name and its member fans."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            members = sorted(user_input[CONF_FANS])

            await self.async_set_unique_id(
                f"{DOMAIN}_{'_'.join(member.split('.', 1)[1] for member in members)}"
            )
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=name,
                data={CONF_NAME: name, CONF_FANS: members},
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): TextSelector(),
                vol.Required(CONF_FANS): EntitySelector(
                    EntitySelectorConfig(domain=fan.DOMAIN, multiple=True)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return OptimisticFanGroupOptionsFlow()


class OptimisticFanGroupOptionsFlow(OptionsFlow):
    """Edit the member fans of an existing group."""

    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            return self.async_create_entry(
                title=name,
                data={
                    CONF_NAME: name,
                    CONF_FANS: sorted(user_input[CONF_FANS]),
                },
            )

        current_name = self.config_entry.options.get(
            CONF_NAME, self.config_entry.data.get(CONF_NAME, self.config_entry.title)
        )
        current_members = self.config_entry.options.get(
            CONF_FANS, self.config_entry.data.get(CONF_FANS, [])
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=current_name): TextSelector(),
                vol.Required(
                    CONF_FANS, default=current_members or vol.UNDEFINED
                ): EntitySelector(
                    EntitySelectorConfig(domain=fan.DOMAIN, multiple=True)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

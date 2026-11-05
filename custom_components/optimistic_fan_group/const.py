"""Constants for the Optimistic Fan Group integration."""

DOMAIN = "optimistic_fan_group"

ATTR_PERCENTAGE = "percentage"
ATTR_DIRECTION = "direction"
ATTR_OSCILLATING = "oscillating"

CONF_FANS = "fans"

DEFAULT_NAME = "Optimistic Fan Group"

# Service to force a re-sync between the optimistic group state and its
# real member entities.
SERVICE_SYNC = "sync"

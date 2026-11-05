# Optimistic Fan Group 🌀

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=XavierT&repository=optimistic-fan-group&category=integration)
[![Open your Home Assistant instance and start a new automation.](https://my.home-assistant.io/badges/developer_tools.svg)](https://my.home-assistant.io/redirect/developer_tools/)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A custom **Home Assistant** integration providing a **Fan Group with an optimistic
state cache** — designed to fix the latency and erratic state feedback of
connected fans (Tuya / LocalTuya / Wi-Fi fans).

---

## 🔥 The problem

Fans controlled by cloud or flaky Wi-Fi protocols (Tuya, LocalTuya, Tuya local,
etc.) often suffer from:

- **Slow responses**: you press "ON", and the state only changes several
  seconds later — if it changes at all.
- **Erratic state feedback**: the fan briefly reports "off" while it is
  actually turning on, or the speed percentage bounces back to its old value
  before catching up.
- **Grouping issues**: grouping several slow fans multiplies the lag, since
  Home Assistant waits for each member to confirm its new state.

## ✅ The solution: an optimistic group

`optimistic_fan_group` creates a virtual `fan.*` entity that groups one or
more existing fans. It behaves like a normal fan, but with an **optimistic
cache**:

1. You send a command (ON/OFF, speed %, direction, oscillation).
2. The command is **immediately forwarded to every member fan**.
3. **The group entity updates its own state instantly** — it does **not** wait
   for the network nor for the real state reported by the devices.
4. The optimistic state is kept in memory until you change it (or explicitly
   re-synchronize it).

The result: instant, perfectly consistent feedback in the UI, no matter how
slow the underlying devices are. The entity also sets `assumed_state = true`,
so Home Assistant displays the "assumed state" indicator 🚩, honestly telling
you the value may not yet match reality.

> A `optimistic_fan_group.sync` service is available to discard the cache and
> reload the real state of the members when you want to check reality.

---

## 📦 Installation

### Method 1 — Automatic, via HACS (recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed.
2. Click the badge below to open this repository directly inside HACS, or go to
   **HACS > Integrations > ⋮ (menu) > Custom repositories** and add:

   | Field | Value |
   |---|---|
   | Repository URL | `https://gitlab.com/XavierT/optimistic-fan-group` |
   | Category | **Integration** |

   [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=XavierT&repository=optimistic-fan-group&category=integration)

3. Click **DOWNLOAD**, pick the latest version, then **download**.
4. Restart Home Assistant when prompted.

### Method 2 — Manual

1. Copy the `custom_components/optimistic_fan_group` folder into your Home
   Assistant `config` directory:

   ```
   <config>/
   └── custom_components/
       └── optimistic_fan_group/
           ├── __init__.py
           ├── config_flow.py
           ├── const.py
           ├── fan.py
           ├── manifest.json
           ├── services.yaml
           ├── strings.json
           └── translations/
               └── fr.json
   ```

2. Restart Home Assistant.

---

## ⚙️ Configuration

### Via the UI (recommended)

1. Go to **Settings > Devices & services > + Add integration**.
2. Search for **Optimistic Fan Group**.
3. Give the group a **name** (it will create the entity `fan.<name>`).
4. Select one or more **fan entities** (`fan.*`) as members of the group.
5. Done — the new group entity appears immediately.

**To change the member list later:**
**Settings > Devices & services > your group > ⚙️ Configure**.

### Via YAML (optional fallback)

The integration also supports the legacy `fan` platform configuration in
`configuration.yaml`:

```yaml
fan:
  - platform: optimistic_fan_group
    name: Bedroom Fans
    fans:
      - fan.bedroom_tuya_fan
      - fan.bedroom_desk_fan
```

> Note: the UI configuration flow is the recommended path; YAML is provided as
> a fallback for automations/templating enthusiasts.

---

## 🎛️ Supported features

| Feature | Optimistic behaviour |
|---|---|
| `TURN_ON` / `TURN_OFF` | State flips immediately, command forwarded to all members |
| `SET_SPEED` (`percentage`) | Percentage stored instantly, forwarded to all members |
| `DIRECTION` (forward/reverse) | Direction stored instantly |
| `OSCILLATE` | Oscillation flag stored instantly |
| `TOGGLE` | Derived from the optimistic state |

The group is available as long as at least one member is known to Home
Assistant.

## 🔁 Re-synchronize

The optimistic cache can drift from reality if a device is manually switched
off (wall switch, IR remote...). Two options:

- Call the service `optimistic_fan_group.sync` on the group entity to reload
  the real member state into the group.
- Or simply send any command again — the optimistic state will overwrite the
  cache.

Example service call:

```yaml
service: optimistic_fan_group.sync
target:
  entity_id: fan.bedroom_fans
```

## 💡 Automation example

```yaml
alias: "Night mode - silent group"
trigger:
  - platform: time
    at: "22:30:00"
action:
  - service: fan.set_percentage
    target:
      entity_id: fan.bedroom_fans
    data:
      percentage: 30
```

Because the group state is optimistic, the resulting state change is
emitted **instantly**, so dashboards and automations reacting to
`fan.bedroom_fans` never lag.

---

## 🛠️ Development

```bash
# Lint
flake8 custom_components/optimistic_fan_group --max-line-length=100
black custom_components/optimistic_fan_group

# Validate manifest (hassfest)
pip install homeassistant
python -m script.hassfest --requirements --integration-path custom_components/optimistic_fan_group
```

CI (`.gitlab-ci.yml`) runs `flake8`, `black` and `hassfest` on every push.

## 📄 License

Released under the [MIT License](LICENSE).

---

*This integration was generated with the help of an AI agent (OpenHands) on
behalf of the repository owner.*
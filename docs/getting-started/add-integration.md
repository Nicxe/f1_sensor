---
id: add-integration
title: Configure F1 Sensor
description: Choose your data, enable live features, and find the entities created by F1 Sensor.
---

Choose the data you want on your dashboard. Complete [installation and restart](/getting-started/installation) first, then start the setup flow:

[![Open your Home Assistant instance and start configuration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=f1_sensor)

:::info
During installation, you can choose exactly which sensors you want to include in your setup.
This gives you control over which data points to load, for example, only the next race and weather, without standings or calendar.

You can always change this selection later by reconfiguring the integration via Settings > Devices & Services in Home Assistant.
:::
:::info[Finding entities after setup]
This documentation always refers to the standard `entity_id`, for example `sensor.f1_track_status` or `binary_sensor.f1_safety_car`.

Display names in Home Assistant can be localized, and older installations may already have different registry IDs. When you search in Home Assistant, search for the `f1_` suffix or check the entity’s `entity_id` in the entity settings instead of relying on the display name alone.
:::

## Configuration choices

The setup form lets you choose how much F1 data Home Assistant should create and update.

| Setting | What to choose |
| --- | --- |
| **Device name** | Keep the default unless you run multiple F1 Sensor entries |
| **Enabled sensors** | Select the static, live, and helper entities you want Home Assistant to create |
| **Enable live F1 API** | Turn this on for live session status, track status, Safety Car, Race Control, weather, timing, tyres, and incident alerts |
| **First day of race week** | Choose when `binary_sensor.f1_race_week` should turn on for your dashboards and automations |
| **Connect F1TV access with Token Helper** | Optional. Use this only when you want extra live-auth features such as live Track Map, Pit Stops, Team Radio, Championship Prediction, or earlier incident candidates |

:::info[F1TV Auth is optional]
Public live timing works without F1TV Auth. Leave F1TV pairing off if you only need schedules, standings, public live timing, Race Control, weather, driver timing, tyres, and confirmed incident alerts.
:::

### Manual Configuration

If the button above does not work, you can also perform the following steps manually:

1. Browse to your Home Assistant instance.
2. Go to **Settings > Devices & Services**.
3. In the bottom right corner, select the **Add Integration** button.
4. From the list, select **F1 Sensor**.
5. Follow the on-screen instructions to complete the setup.


## Device Structure

The integration organizes all entities across **six dedicated sub-devices**, which appear under **Settings > Devices & Services > Devices** in Home Assistant.

| Device | What it contains |
| --- | --- |
| **Race** | Next race info, track time, race week indicator, season calendar |
| **Championship** | Driver and constructor standings, points progression, championship predictions* |
| **Session** | Session status, track status, safety car, weather, timing sensors, starting grid, formation start*, overtake mode, straight mode |
| **Drivers** | Driver list, tyres, tyre statistics, driver positions, favorite driver, pit stops*, team radio* |
| **Officials** | Race control messages, FIA documents, track limits, investigations |
| **System** | Live delay, calibration controls, replay controls, live timing connectivity, F1TV token status and controls |

*Entities marked with an asterisk depend on either [Replay Mode](/features/replay-mode) or optional [F1TV Auth](/features/f1tv-auth), depending on whether you are using historical replay data or extra live timing data.

Each device exposes its own set of [device automation triggers](/automation#device-automation-triggers), making it straightforward to build automations directly from the UI without writing YAML.
For device changes in older releases, see [upgrading an existing setup](/getting-started/release-channels#upgrading-an-existing-setup).

---

## Live data setup

Enable **Enable live F1 API** when you want Home Assistant to create and update live session entities. When live data is enabled, you can set an initial delay to better align live updates with your TV broadcast.

For detailed instructions on syncing with your TV, including guided calibration, see [Live Delay](/features/live-delay).

Public live timing works without F1TV Auth. This covers the normal live features most users need, including session status, track status, Safety Car, Race Control, weather, driver timing, tyres, and confirmed incident alerts.

Optional [F1TV Auth](/features/f1tv-auth) can be paired with the [F1TV Token Helper](/help/f1tv-token-helper) when you want extra live timing features during a real live session. It can enable or improve features such as [Track Map](/features/track-map), Pit Stops, Team Radio, Championship Prediction, formation start data, and earlier incident candidates.

Replay Mode is a separate mode. It can show some data that requires F1TV Auth during live sessions because replay uses Formula 1's public session archive after the session has completed.

For the practical F1TV Auth setup, see [F1TV Auth Setup](/help/f1tv-auth-setup). For incident behavior, see [Incident Detection](/features/incident-detection).
## Check your setup

1. Open the **Race** device and find the Next race entity.
2. Check that it has a race name and schedule attributes.
3. Open **Session** if you enabled live data. An inactive state between sessions is normal.
4. Add a [first dashboard card](/getting-started/first-dashboard).

Use [Live Delay](/features/live-delay) to measure your own broadcast delay. No universal delay fits every service.

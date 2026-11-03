---
id: add-integration
title: Configure F1 Sensor
description: Choose your data, enable live features, and find the entities created by F1 Sensor.
---

Choose the live features and Home Assistant entities you need, then build your dashboard. Complete [installation and restart](/getting-started/installation) first.

[![Open your Home Assistant instance and start configuration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=f1_sensor)

## Manual Configuration

If the button above does not work, you can also perform the following steps manually:

1. Browse to your Home Assistant instance.
2. Go to **Settings > Devices & Services**.
3. In the bottom right corner, select the **Add Integration** button.
4. From the list, select **F1 Sensor**.
5. Follow the on-screen instructions to complete the setup.

## Choose modules and sensors separately

Add the modules you want in the **F1 Sensor** card. Their [data is available automatically](/features/card-data-and-sensors), independently of sensor exposure. There is no separate card-data checklist.

Select only the entities you want to use in Home Assistant, such as Next race and weather for standard cards, or Track Status for a light automation. You can change sensor choices later in the integration settings. Keep entities used by automations, templates or older F1 cards; reducing the selection can remove their registry entries.

Existing installations keep their sensor choices and start normally after updating. See [the automatic card data upgrade notice](/getting-started/required-data-choice).

## Configuration choices

The setup form controls live access and the entities exposed in Home Assistant. The modular card gets data for its modules automatically; sensor selection is for automations, templates, standard cards and older F1 cards.

| Setting | What to choose |
| --- | --- |
| **Device name** | Keep the default unless you run multiple F1 Sensor entries |
| **Enabled sensors** | Select the static, live, and helper entities you want Home Assistant to create |
| **Enable live F1 API** | Turn this on for live session status, track status, Safety Car, Race Control, weather, timing, tyres, and incident alerts |
| **First day of race week** | Choose when `binary_sensor.f1_race_week` should turn on for your dashboards and automations |
| **Connect F1TV access with Token Helper** | Optional. Connect account access for Replay Mode, Formula 1 timing archives, or extra live features such as Track Map, Pit Stops, Team Radio, Championship Prediction and earlier incident candidates |

## Live data setup

Enable **Enable live F1 API** for live session data, whether you display it in modular cards or selected entities. Public live timing works without F1TV pairing: session status, track flags, Safety Car, Race Control, weather, driver timing, tyres and confirmed incident alerts are available when the source publishes them.

When live data is enabled, you can set an initial delay and then [calibrate Live Delay with your TV](/features/live-delay). Measure your own broadcast; no universal delay fits every service.

Optional [F1TV access](/features/f1tv-auth) can enable or improve Track Map, Pit Stops, Team Radio, Championship Prediction, formation start and earlier incident candidates when the account receives the required live feeds. For practical pairing steps, use [Connect optional F1TV access](/help/f1tv-auth-setup).

Replay Mode is separate. It downloads the completed-session timing archive using connected Formula 1 account access. It can show data that needed extra permissions live, but only when the archive contains it. See [Replay Mode](/features/replay-mode) and [Incident Detection](/features/incident-detection).

## Check your setup

1. Add the [Race weekend dashboard preset](/getting-started/first-dashboard). Schedule information is useful between sessions.
2. If you selected the Next race entity, open the **Race** device and check its race name and schedule attributes.
3. If you enabled live data, an inactive live state between sessions is normal. Use [data availability](/features/f1tv-auth) before treating waiting as a setup error.
4. For an automation, confirm that its required entities are selected, then use a [device trigger or blueprint](/automation).

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

## Find your entities

This documentation always refers to the standard `entity_id`, for example `sensor.f1_track_status` or `binary_sensor.f1_safety_car`.

Display names in Home Assistant can be localized, and older installations may already have different registry IDs. When you search in Home Assistant, search for the `f1_` suffix or check the entity’s `entity_id` in the entity settings instead of relying on the display name alone.

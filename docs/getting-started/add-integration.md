---
id: add-integration
title: Configuration
---

# Configuration

To add the integration to your Home Assistant instance, use the button below:

[![Open your Home Assistant instance and start configuration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=f1_sensor)


:::info
During installation, you can choose exactly which sensors you want to include in your setup.
This gives you control over which data points to load, for example, only the next race and weather, without standings or calendar.

You can always change this selection later by reconfiguring the integration via Settings > Devices & Services in Home Assistant.
::::


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
| **Championship** | Driver and constructor standings, points progression, championship predictions |
| **Session** | Session status, track status, safety car, weather, timing sensors, formation start, overtake mode, straight mode |
| **Drivers** | Driver list, tyres, tyre statistics, driver positions, team radio |
| **Officials** | Race control messages, FIA documents, track limits, investigations |
| **System** | Live delay, calibration controls, replay controls, live timing connectivity |

Each device exposes its own set of [device automation triggers](/automation#device-automation-triggers), making it straightforward to build automations directly from the UI without writing YAML.

:::warning Upgrading from v3 to v4
After updating to v4.0.0, the original single F1 Sensor device will appear empty in Home Assistant and should be removed manually from **Settings > Devices & Services > Devices**.

All entity IDs remain unchanged, so automations and dashboard cards that reference entities by their ID will continue to work without modification. However, dashboard views organized by device and any device-based conditions or triggers in automations will need to be updated to reference the new sub-devices.
:::

---

## Live data setup

When enabling live data, you can set an initial delay to better align live updates with your TV broadcast.

For detailed instructions on syncing with your TV, including guided calibration, see [Live Delay](/features/live-delay).

:::tip Quick start
A typical streaming delay is 30–45 seconds. You can always fine-tune this later using the [Live Delay](/features/live-delay) feature.
:::
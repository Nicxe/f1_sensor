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


## Live data setup

When enabling live data, you can set an initial delay to better align live updates with your TV broadcast.

For detailed instructions on syncing with your TV, including guided calibration, see [Live Delay](/features/live-delay).

:::tip Quick start
A typical streaming delay is 30–45 seconds. You can always fine-tune this later using the [Live Delay](/features/live-delay) feature.
:::
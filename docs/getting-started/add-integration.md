---
id: add-integration
title: Configuration
description: To add the integration to your Home Assistant instance
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

- **Live update delay (seconds)**  
  Lets you delay delivery of live messages to better align with what you see on TV or streaming.  

  Typical broadcast delays:  
  - Broadcast TV (satellite/cable/terrestrial): ~5–10 seconds behind  
  - Streaming services: ~20–45 seconds behind, sometimes more  
  - Sports cable/OTT providers: 45–60 seconds or more depending on provider  

  By setting the delay accordingly, your Home Assistant automations (for example flashing lights on a red flag) can sync more closely with the live pictures you are watching.

  ::::tip 
  During the broadcast, they always show the moment the race clock flips to the start time, for example 15:00:00. If you look up an [atomic clock online](https://time.is/), you’ll have an exact reference. Watch the time when the broadcast clock hits the start. So when the broadcast clock shows 15:00:00 and the formation lap starts, the atomic clock reads 15:00:30. Then set a 30-second delay in the configuration.
  ::::
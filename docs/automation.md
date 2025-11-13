---
id: automation
title: Automation
---


### Synchronize your lights with the flag status

The Formula 1 Track Status Blueprint for Home Assistant lets you synchronize your lights with the live race flag status. 

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FEvertJob%2FF1-Blueprint%2Fblob%2Fmain%2Fblueprint%2Ff1.yaml)

![F1SensorFlag-ezgif com-video-to-gif-converter (5)](https://github.com/user-attachments/assets/18a74679-76e2-4d10-8a0d-d3f111c42593)

*It is now maintained by [EvertJob](https://github.com/EvertJob/). You can find the latest version and full setup instructions here: 👉 [F1-Blueprint](https://github.com/EvertJob/F1-Blueprint)*

---

### Race Control Event Notifications

This automation listens for f1_sensor_race_control_event events and sends the Message field from each event as a notification in Home Assistant. It provides real-time updates from Race Control, such as flag changes or incident reports.

```yaml
alias: F1 - Race Control Notification
description: Sends Race Control messages as notifications in Home Assistant
trigger:
  - platform: event
    event_type: f1_sensor_race_control_event
condition: []
action:
  - service: notify.persistent_notification
    data:
      title: "Race Control"
      message: "{{ trigger.event.data.message.Message }}"
mode: queued
max: 10
```
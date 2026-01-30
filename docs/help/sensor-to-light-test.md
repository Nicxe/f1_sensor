---
id: Sensor-to-Light Integration Test
title: Sensor-to-Light Integration Test
---

## Overview

This test will allow you to determine whether your light is capable of responding to the sensor state.
------------------------------------------------------------------------

## Prerequisites

Before running the tests, make sure you have:

-   Home Assistant installed and running
-   A supported smart light bulb (Tested with: Govee RGBWW -- Model
    H6008)
-   F1 Sensor integration configured
-   Developer Tools access enabled

------------------------------------------------------------------------

## Test Process

### Track Sensors Configuration

1. Set the Session State to `F1_session_status` 
1. Set the Track state to `F1_track_status` 
1. Set Race phase to `Race has ended`

![Track sensors section](https://github.com/user-attachments/assets/test_track_sensors.png)

------------------------------------------------------------------------

### Light Settings Configuration

1. Search for `Light to Control` and choose your light (Govee Bulb 1 in this case), 
1. Set the Brightness and trasition time as your preference.

![light settings section](https://github.com/user-attachments/assets/test_light_settings.png)

------------------------------------------------------------------------

## Using [developer tools](https://my.home-assistant.io/redirect/developer_states/):

### Simulating Session Status

1. Select an entity: `sensor.f1_session_status` 
1. Set the State to: ended
1. Click on `Set state` button

![Test 3](https://github.com/user-attachments/assets/DevTools_session_status.png)

------------------------------------------------------------------------

### Simulating Track Status

Allowed values:
CLEAR, YELLOW, RED, VSC, SC

1. Select an entity: `sensor.f1_track_status` 
1. Set the State to  <strong>one </strong> of the available options: `"CLEAR","YELLOW","RED","VSC", "SC" `
1. Click on `Set state` button

![Test 4](https://github.com/user-attachments/assets/DevTools_track_status.png)

### Expected Results

| Track Status   | Expected Behavior| 
| :-------------- | :-------------------| 
| CLEAR          | Green light| 
| YELLOW         | Yellow light| 
| RED            | Red light| 
| VSC            | Flashing| 
| SC             | Flashing| 

---
id: installation
title: Installation & Configuration
---

# Installation & Configuration

Get up and running with F1 Sensor in just a few minutes.  
This guide walks you through installation and configuration in Home Assistant, step by step.



## Overview, how it works



1. Install the integration  
2. Add it to Home Assistant  
3. Select which sensors you want to use  


![Install and configure](/img/install_config.gif)

---

## Step 1 - Install the integration

### Recommended, install via HACS

The easiest way to install and keep F1 Sensor up to date.

#### Option A, My Home Assistant

Click the button below to automatically add the repository to HACS.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Nicxe&repository=f1_sensor&category=integration)

#### Option B, Directly in HACS

1. Open **HACS** in Home Assistant  
2. Search for **F1 Sensor**  
3. Click **Download**

:::tip
When installed through HACS, you will automatically receive update notifications when new releases are available.
:::


<details>
  <summary>Manual installation</summary>

Use this option if you do not use HACS.
1. Download the latest release  
   https://github.com/Nicxe/f1_sensor/releases  
   Download `f1_sensor.zip`
2. Extract the archive and copy the `f1_sensor` folder to  
   `config/custom_components/`
3. Restart Home Assistant


</details>


---

## Step 2 - Add the integration to Home Assistant

Once the installation is complete, the integration must be added.

[![Open your Home Assistant instance and start configuration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=f1_sensor)

or

1. Go to **Settings > Devices & Services**  
2. Click **Add Integration** in the bottom right  
3. Select **F1 Sensor**  
4. Follow the on screen instructions

---

## Step 3 - Select which sensors to create

During configuration, you choose exactly which data you want to include.

:::info
For example, you can choose to only create sensors for the next race and weather, without calendar or standings.

You can always change this later via  
**Settings > Devices & Services > F1 Sensor > Reconfigure**
:::

![Resources fonts](/img/reconfigure.png)

---

## Done

Once configuration is complete, the sensors are created automatically and are ready to be used in dashboards, automations, and templates.

---

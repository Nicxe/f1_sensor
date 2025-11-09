---
id: installation
title: Installation
description: Learn how to install the Navbar Card in your Home Assistant setup
---

# Installation Guide

There are several ways to install the F1 Sensor to Home Assistant. Choose the method that works best for you.

## Option 1: Install via HACS (Recommended)

The easiest way to install and keep F1 Sensor updated is through HACS (Home Assistant Community Store).

### Using My Home Assistant

Click the button below to automatically add the repository to HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Nicxe&repository=f1_sensor&category=integration)


### Manual HACS Installation

1. Open **HACS** in your Home Assistant instance
2. Search for "F1 Sensor"
3. Click the download button. ⬇️


:::tip Automatic Updates
When installed through HACS, you'll automatically get notified when updates are available!
:::

<br/>

---

## Option 2: Manual Installation

If you prefer to install the integration manually or don't use HACS, follow these steps:

1. Download the latest release:
   - Go to the **[GitHub Releases](https://github.com/Nicxe/f1_sensor/releases)**
   - Download `f1_sensor.zip`

2. Copy to Home Assistant:
   - Extract the downloaded files and place the `f1_sensor` folder in your Home Assistant `custom_components` directory (usually located in the `config/custom_components` directory).

3. Restart your Home Assistant instance to load the new integration.

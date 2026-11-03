---
id: installation
title: Install F1 Sensor
description: Install F1 Sensor with HACS, add it to Home Assistant, and build your first Formula 1 dashboard.
---

Bring Formula 1 schedules, results and live timing into Home Assistant. Start with the stable release; you can build your first dashboard without an F1TV subscription or a live session.

## How it works

1. **Install** F1 Sensor and restart Home Assistant.
2. **Configure** the data you want to use.
3. **Build** your first dashboard with the included card.

## Step 1 - Install the integration

### Recommended, install via HACS

Open the repository in HACS:

[![Open F1 Sensor in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Nicxe&repository=f1_sensor&category=integration)

#### Option A, My Home Assistant

Use the button above, choose your Home Assistant instance and download the latest stable version of **F1 Sensor**. **Restart Home Assistant** after the download completes.

#### Option B, Directly in HACS

1. Open **HACS** and search for **F1 Sensor**.
2. Open the integration and select **Download**.
3. **Restart Home Assistant** after the download completes.

HACS notifies you about future updates. See [release channels](/getting-started/release-channels) if you want to test a beta.

<details>
<summary>Manual installation without HACS</summary>

1. Open [F1 Sensor releases](https://github.com/Nicxe/f1_sensor/releases/latest).
2. Download the release asset **f1_sensor.zip**.
3. Extract it so the integration files are in `config/custom_components/f1_sensor/`.
4. Restart Home Assistant.

Use the release asset rather than a source-code archive; it contains the files needed by Home Assistant.

</details>

## Step 2 - Add the integration to Home Assistant

After restarting, open **Settings → Devices & services → Add integration** and search for **F1 Sensor**. The [configuration guide](/getting-started/add-integration) explains the choices in the setup form.

[![Start F1 Sensor configuration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=f1_sensor)

## Step 3 - Choose your data needs {/* #step-3---select-which-sensors-to-create */}

For the included modular dashboard card, add the modules you want; their data is automatic and does not require matching sensor entities. Start with the **Race weekend** preset in [Your first dashboard](/getting-started/first-dashboard).

Keep sensors selected when you use them in automations, templates, standard cards or older F1 cards. Enable **Enable live F1 API** for live timing, flags and live automations. You can change settings later through **Settings → Devices & services → F1 Sensor → Reconfigure**; [configuration](/getting-started/add-integration) explains the choices.

![The Reconfigure action for F1 Sensor in Home Assistant](/img/reconfigure.png)

*Use Reconfigure to change enabled features after installation.*

F1TV pairing is optional. See [what works with each data mode](/features/f1tv-auth#availability-matrix) before adding access for a particular feature.

## Done

Open the integration and check its devices and any selected entities. The Race weekend dashboard can show schedule data even when no session is running; live data can wait until the next session.

The F1 Sensor dashboard card is included and registered automatically. Continue with **[Your first dashboard](/getting-started/first-dashboard)**.

If F1 Sensor is missing from Add integration, confirm the download completed, restart Home Assistant and refresh the browser. For further checks, open [troubleshooting](/help/overview).

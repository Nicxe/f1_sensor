---
id: installation
title: Install and update the F1 Sensor card
description: Load the bundled F1 Sensor dashboard card and troubleshoot its browser resource.
---

The **F1 Sensor** dashboard card is bundled with the integration. You do not need a separate HACS dashboard repository.

## Install the card

1. [Install or update F1 Sensor](/getting-started/installation).
2. Restart Home Assistant so the integration can register its dashboard resource.
3. Open a dashboard and select **Edit dashboard > Add card**.
4. Search for **F1 Sensor** and select the card.
5. Choose a preset, review the preview and save.

The integration registers `/local/f1-sensor-live-data-card/f1-sensor-live-data-card.js?v=...` as a JavaScript module. With one F1 Sensor installation, the card selects it automatically.

## Update the card

Update the F1 Sensor integration, restart Home Assistant and reload the dashboard. If the editor or card still looks older, hard refresh the browser and check for duplicate resources before changing the card configuration.

:::tip[Keep one managed resource]
The current card and its supporting files are delivered together. Keep the integration-managed resource and remove stale copies from an earlier standalone card installation.
:::

## Remove a standalone resource

Confirm that the bundled **F1 Sensor** card opens before removing an old standalone resource.

1. Update F1 Sensor, restart Home Assistant and add a new **F1 Sensor** card.
2. Confirm that the card renders and its visual editor opens.
3. In HACS, remove the old **F1 Sensor Live Data Card** dashboard repository if it is still installed.
4. Open **Settings > Dashboards**, open the three-dot menu and select **Resources**.
5. Remove stale entries such as `/local/f1-sensor-live-data-card.js` or `/hacsfiles/f1-sensor-live-data-card/...`.
6. Keep the integration-managed `/local/f1-sensor-live-data-card/f1-sensor-live-data-card.js?v=...` JavaScript module.
7. Restart Home Assistant or reload dashboard resources, then hard refresh the browser.

:::warning[Old standalone resources detected]
This repair means that Home Assistant found an outdated resource URL. It does not mean that the F1 Sensor integration or its entities should be removed.
:::

## Card loading checks

| What you see | Check next |
| --- | --- |
| **F1 Sensor** is missing from the picker | Confirm that the integration is loaded, restart Home Assistant and reload the browser. |
| **Custom element doesn't exist** | Confirm that the managed resource exists and uses the **JavaScript Module** type. Remove duplicate standalone URLs. |
| The editor still looks older after an update | Hard refresh the browser, then check for a cached or duplicate resource. |
| The card asks you to choose an installation | Open the visual editor and select the intended F1 Sensor installation. |
| A module explains that data is unavailable | Check whether its source entity and integration feature are enabled. Some live data is unavailable between sessions. |
| Every F1 module fails after an update | Record the integration version and browser error, then enable [debug logging](/help/debug-logging). |

Do not remove a working integration to fix a browser resource problem. The integration, its entities and the dashboard JavaScript are separate parts of the setup.

## Manual resource fallback

<details>
<summary>Use only when automatic resource registration is unavailable</summary>

Copy the complete bundled directory from `custom_components/f1_sensor/www/f1-sensor-live-data-card/` to `config/www/f1-sensor-live-data-card/`. Keep all subdirectories and companion files together.

Add this resource under **Settings > Dashboards > Resources**:

| Field | Value |
| --- | --- |
| URL | `/local/f1-sensor-live-data-card/f1-sensor-live-data-card.js` |
| Resource type | **JavaScript Module** |

For a YAML-managed resource list:

```yaml
lovelace:
  resources:
    - url: /local/f1-sensor-live-data-card/f1-sensor-live-data-card.js
      type: module
```

Reload dashboard resources and refresh the browser after copying an update.

</details>

## Next steps

- [Add and configure the card](/cards/cards-overview)
- [Build a custom card](/cards/modular)
- [Move from a deprecated card](/cards/modular-migration)

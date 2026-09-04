---
id: installation
title: Card installation and updates
description: Install the bundled F1 Sensor dashboard cards, update them safely, and remove old standalone resources.
---

The F1 Sensor dashboard cards are included with the integration. Install F1 Sensor once, then choose the cards you want in the Home Assistant dashboard editor.

## Bundled installation

1. [Install or update F1 Sensor](/getting-started/installation).
2. Restart Home Assistant so the integration can load the bundled assets.
3. Open your dashboard and select **Edit dashboard > Add card**.
4. Search for **F1** and choose a [dashboard card](/cards/cards-overview).
5. Select its data sources if needed, then select **Save**.

The integration registers the dashboard resource automatically as a JavaScript module. You do not need to add the old **F1 Sensor Live Data Card** repository to HACS separately.

For your first card, choose [Next Race](/cards/next-race). Its schedule and countdown work between sessions and do not need F1TV Auth.

## Update existing cards

Update the F1 Sensor integration, restart Home Assistant and reload your dashboard in the browser. Existing `custom:f1-...` card types remain valid, and your dashboard configuration is preserved.

If the interface still looks like an older version, follow the [loading checks](#card-loading-checks) before replacing any card configuration.

## Migrate from the standalone card

Confirm that the bundled cards work before removing the standalone installation.

1. Update F1 Sensor, restart Home Assistant and open a dashboard containing an F1 card.
2. Check that the card renders and can open its visual editor.
3. Open **HACS** and find **F1 Sensor Live Data Card** in the dashboard or frontend section.
4. Remove that standalone repository.
5. Open **Settings > Dashboards**, open the three-dot menu and select **Resources**.
6. Remove leftover standalone resource entries such as `/local/f1-sensor-live-data-card.js` or `/hacsfiles/f1-sensor-live-data-card/...`.
7. Keep the integration-managed resource at `/local/f1-sensor-live-data-card/f1-sensor-live-data-card.js?v=...` with type **JavaScript Module**.
8. Restart Home Assistant or reload dashboard resources, then hard refresh the browser.

:::info[Automatic resource migration]
F1 Sensor updates an old resource entry when it can. If several old entries exist, extra entries may require manual cleanup. Keep the working integration-managed resource.
:::

:::warning[Old standalone resources repair]
The **Old standalone F1 live data card resources detected** repair points to stale resource URLs. Complete the migration above after checking that the bundled cards load. This repair does not mean that you need to remove the integration or its entities.
:::

The legacy `custom:f1-session-archive-card` type also remains compatible. It opens the unified [Results card](/cards/results) in Archive mode; new dashboards can use `custom:f1-last-race-results-card` with `default_scope: archive`.

## Card loading checks

| What you see | Check next |
| --- | --- |
| No F1 cards in the picker | Confirm that F1 Sensor is installed and loaded, then restart Home Assistant and reload the browser. |
| **Custom element doesn't exist** | Check that the managed resource exists and has type **JavaScript Module**. Look for a stale standalone URL. |
| An old card interface after updating | Reload the browser, then check for duplicate resources from the standalone installation. |
| **Entity not found** | Select the matching source in the card editor and confirm that the entity is enabled in F1 Sensor. See [Entity selection](/cards/shared-options#entity-selection). |
| A live card has no data | Open its reference page and check the session and authentication requirements. No live data between sessions can be normal. |
| All cards fail after an update | Record the integration version and browser error, then follow [debug logging](/help/debug-logging). |

Do not remove a working integration to fix a browser resource problem. The integration, its entities and the dashboard JavaScript resource are separate parts of the setup.

## Manual resource fallback

<details>
<summary>Use only when automatic resource registration is unavailable</summary>

Copy the complete bundled directory from `custom_components/f1_sensor/www/f1-sensor-live-data-card/` to `config/www/f1-sensor-live-data-card/`. Keep its subdirectories and companion files together; copying only the main JavaScript file is insufficient.

In **Settings > Dashboards**, open the three-dot menu, select **Resources > Add resource**, and enter:

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

Reload dashboard resources and refresh the browser after updating the copied files.

</details>

## Next steps

- [Choose a dashboard card](/cards/cards-overview)
- [Entity selection and shared options](/cards/shared-options)
- [Release channels](/getting-started/release-channels)

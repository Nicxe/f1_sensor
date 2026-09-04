---
id: favorite-driver
title: Follow your favorite driver
description: Select a driver once and use their position, timing and pit activity in dashboards and automations.
---

Favorite Driver follows the driver you choose and gives you one entity for their position and timing. You can also react when that driver gains a place, enters the pits or retires.

## Enable and select

1. Open **Settings → Devices & services → F1 Sensor → Reconfigure**.
2. Enable live data and include **Favorite driver** in the enabled features.
3. Open the **Drivers** device and find `select.f1_favorite_driver`.
4. Choose the driver's three-letter abbreviation when the driver list is available.

The feature is opt-in for both new and existing installations. Your selection is saved for this integration entry and restored after a restart. Select **No driver** to clear it.

## Add it to a dashboard

Use `sensor.f1_favorite_driver` in a standard Home Assistant entity card. Its state is the selected driver's position; its attributes add timing, tyre, pit and team details. The sensor can be unavailable until the selected driver appears in timing data.

```yaml
type: entities
entities:
  - select.f1_favorite_driver
  - sensor.f1_favorite_driver
```

Use your existing entity IDs if Home Assistant assigned different ones.

## React to that driver's session

When you create a device automation on the **Drivers** device, choose a Favorite Driver trigger for position gained/lost, entered/exited pits or retired. Start with one trigger and a simple notification, then add your usual presence or TV conditions.

The triggers follow [Live Delay](/features/live-delay). Replayed changes can trigger actions again after rewinding; avoid treating them as a unique live alert.

## If no driver data appears

Confirm the feature and live data are enabled, a driver is selected, and a live or replay session contains that driver. Selecting a name does not create historical timing that the source did not publish.

See the [entity reference](/entities/favorite-driver) and [device triggers](/reference/device-triggers) for exact fields and behavior.

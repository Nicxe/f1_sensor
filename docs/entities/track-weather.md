---
id: track-weather
title: "Track Weather"
description: "Current on-track weather (air temp, track temp, rainfall, wind speed, etc.) \u2014 state, attributes, and examples for F1 Sensor."
---

Current on-track weather (air temp, track temp, rainfall, wind speed, etc.). Use `sensor.f1_track_weather` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

Live trackside weather from F1 Live Timing. Updates only in direct connection with a session, and remains unchanged otherwise.

**State**
- Number: air temperature in Home Assistant's selected temperature unit, or `unknown`.

**Example**
```text
18.6
```

:::info
Home Assistant may display the sensor state in another temperature unit, such as Fahrenheit, when your system uses that unit. The weather attributes remain in the documented source units, such as Celsius for temperatures and meters per second for wind speed.
:::

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| air_temperature | number | Air temperature (°C) |
| air_temperature_unit | string | “celsius” |
| humidity | number | % RH |
| humidity_unit | string | “%” |
| pressure | number | hPa |
| pressure_unit | string | “hPa” |
| rainfall | number | mm |
| rainfall_unit | string | “mm” |
| track_temperature | number | Track temperature (°C) |
| track_temperature_unit | string | “celsius” |
| wind_speed | number | m/s |
| wind_speed_unit | string | “m/s” |
| wind_from_direction_degrees | number | Wind direction (degrees) |
| wind_from_direction_unit | string | “degrees” |
| measurement_inferred | boolean | True if payload had no explicit timestamp |
:::info[INFO]
Updates approximately every minute during an active session.
:::



## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)

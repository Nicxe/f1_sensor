---
id: next-race-weather
title: "Next Race Weather"
description: "Native current conditions and forecasts for the next race circuit \u2014 state, attributes, and examples for F1 Sensor."
---

Native current conditions and forecasts for the next race circuit. Use `weather.f1_weather` in dashboards, templates, and automations.

This reference covers the state and attributes. For setup, see [Configuration](/getting-started/add-integration).

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`weather.f1_weather` provides current conditions and native forecasts for the circuit hosting the next race. Its display name includes the circuit and city when both are available, and it updates when the next race destination changes.

**State**

- Home Assistant weather condition, such as `sunny`, `cloudy`, `rainy`, or `lightning-rainy`.

**Example**

```text
partlycloudy
```

**Forecasts**

The entity supports Home Assistant's hourly, daily, and twice-daily forecast types. Forecast values use your Home Assistant unit preferences when displayed in the UI.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| temperature | number | Current air temperature |
| humidity | number | Current relative humidity (%) |
| cloud_coverage | number | Current cloud cover (%) |
| wind_speed | number | Current wind speed |
| wind_gust_speed | number | Current wind gust speed |
| wind_bearing | number | Current wind direction in degrees |
| visibility | number | Current visibility |
| race_start | string | Race start timestamp |
| race_forecast_available | boolean | Whether a forecast for race start is available |
| season | string | Season year for the next race |
| round | string | Round number for the next race |
| race_name | string | Grand Prix name |
| circuit_id | string | Circuit identifier |
| circuit_name | string | Circuit name |
| circuit_locality | string | City/area |
| circuit_country | string | Country |

:::info[Existing weather sensor]
The existing `sensor.f1_weather` remains available for backward compatibility and for bundled cards that compare current conditions with the race-start forecast.
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)

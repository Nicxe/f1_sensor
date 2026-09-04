---
id: weather-summary
title: "Weather Summary"
description: "Weather forecast at next race circuit \u2014 state, attributes, and examples for F1 Sensor."
---

Weather forecast at next race circuit. Use `sensor.f1_weather` in dashboards, templates, and automations.

This reference covers the state and attributes. For setup, see [Configuration](/getting-started/add-integration).

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`sensor.f1_weather` provides compact weather data for the circuit location, both now and at race start.

**State**
- Number: current air temperature in Home Assistant's selected temperature unit, or `unknown`.

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
| season | string | Season year for the next race |
| round | string | Round number for the next race |
| race_name | string | Grand Prix name |
| race_url | string | Ergast race URL |
| circuit_id | string | Circuit identifier |
| circuit_name | string | Circuit name |
| circuit_url | string | Circuit URL |
| circuit_lat | string | Latitude |
| circuit_long | string | Longitude |
| circuit_locality | string | City/area |
| circuit_country | string | Country |
| current_temperature | number | Current air temperature (°C) |
| current_temperature_unit | string | “celsius” |
| current_humidity | number | % RH |
| current_humidity_unit | string | “%” |
| current_cloud_cover | number | % cloud cover |
| current_cloud_cover_unit | string | “%” |
| current_precipitation | number | Selected precipitation amount (mm, best effort) |
| current_precipitation_amount_min | number | Min precip amount (mm) if provided |
| current_precipitation_amount_max | number | Max precip amount (mm) if provided |
| current_precipitation_probability | number | Probability of precipitation (%) when provided |
| current_precipitation_probability_unit | string | “%” |
| current_precipitation_unit | string | “mm” |
| current_wind_speed | number | Wind speed (m/s) |
| current_wind_speed_unit | string | “m/s” |
| current_wind_direction | string | Cardinal abbreviation (e.g., "NW") |
| current_wind_from_direction_degrees | number | Wind direction (degrees) |
| current_wind_from_direction_unit | string | "degrees" |
| current_wind_gusts | number | Wind gust speed (m/s) |
| current_wind_gusts_unit | string | "m/s" |
| current_visibility | number | Visibility (m) |
| current_visibility_unit | string | "m" |
| current_weather_code | number | WMO weather interpretation code |
| current_weather_source | string | "open-meteo" |
| race_temperature | number | Projected air temperature at race start (°C) |
| race_temperature_unit | string | “celsius” |
| race_humidity | number | % RH at race start |
| race_humidity_unit | string | “%” |
| race_cloud_cover | number | % at race start |
| race_cloud_cover_unit | string | “%” |
| race_precipitation | number | Selected precipitation at race start (mm) |
| race_precipitation_amount_min | number | Min precip amount (mm) if provided |
| race_precipitation_amount_max | number | Max precip amount (mm) if provided |
| race_precipitation_probability | number | Probability of precipitation (%) when provided |
| race_precipitation_probability_unit | string | “%” |
| race_precipitation_unit | string | “mm” |
| race_wind_speed | number | Wind speed at race start (m/s) |
| race_wind_speed_unit | string | “m/s” |
| race_wind_direction | string | Cardinal abbreviation |
| race_wind_from_direction_degrees | number | Wind direction (degrees) |
| race_wind_from_direction_unit | string | "degrees" |
| race_wind_gusts | number | Projected wind gust speed at race start (m/s) |
| race_wind_gusts_unit | string | "m/s" |
| race_visibility | number | Projected visibility at race start (m) |
| race_visibility_unit | string | "m" |
| race_weather_code | number | WMO weather interpretation code at race start |
| race_weather_source | string | "open-meteo" |
| race_weather_icon | string | MDI icon name matching weather symbol |


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)

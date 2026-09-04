---
id: issues
title: Recorder and large attributes
description: Understand large-attribute Recorder warnings and keep dashboard data without unnecessary history.
---
Use the [F1 Sensor issue tracker](https://github.com/Nicxe/f1_sensor/issues) for both integration and Live Data Card bugs. For dashboard card problems, select **Live data card** in the issue form component field and include a screenshot or screen recording when the problem is visual.

## Large season-result attributes

The warning concerns stored history, not whether the current sensor can display results.

:::info[Recorder warning]
The sensor may trigger a warning in the Home Assistant logs:

```text
Logger: homeassistant.components.recorder.db_schema
Source: components/recorder/db_schema.py:663
Integration: Recorder
State attributes for sensor.f1_season_results exceed maximum size of 16384 bytes. This can cause database performance issues; Attributes will not be stored
```

The current entity remains usable in dashboards. If you do not need its attribute history, exclude it from Recorder. Merge this into your existing `recorder` configuration; do not add a second top-level `recorder` key:

```yaml
recorder:
  exclude:
    entities:
      - sensor.f1_season_results
```
:::

Restart Home Assistant after changing Recorder configuration. Historical attributes that were not stored cannot be recovered from Recorder later. For another symptom, use [troubleshooting](/help/overview).

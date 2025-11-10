---
id: Issues
title: Known Issues
---

::::caution **`sensor.f1_season_results`**
The sensor may trigger a warning in the Home Assistant logs:

```yaml
Logger: homeassistant.components.recorder.db_schema
Source: components/recorder/db_schema.py:663
Integration: Recorder
State attributes for sensor.f1_season_results exceed maximum size of 16384 bytes. This can cause database performance issues; Attributes will not be stored
```

Despite the warning, the sensor should still work fine for display in the frontend. However, to avoid any database load/performance issues, it is recommended to **exclude this sensor from being recorded** in your `recorder:` config:

```yaml
recorder:
  exclude:
    entities:
      - sensor.f1_season_results
```
::::
---
id: season-results
title: "Season Results"
description: "All season race results \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

All season race results.

<EntityMeta id="season-results" />

<span id="state-and-attributes"></span>

`sensor.f1_season_results` - All results across the current season.

## State

  - Integer: number of races with results.

**Example**
```text
22
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| races | list | For each race: `{round, race_name, results:[...]}` where each result has the same shape as in [Last Race Results](/entities/last-race-results), including the `grid` field |

## Recorder behavior

The integration excludes the large `races` attribute from Recorder. It remains available to dashboards and templates, while Recorder does not store the full season result array. You do not need a Recorder exclusion just to avoid recording that attribute on the current version.

<details>
<summary>Older versions: attribute-size warning and manual exclusion</summary>

Older versions without this automatic attribute exclusion can show this warning in the Home Assistant logs:

```text
Logger: homeassistant.components.recorder.db_schema
Source: components/recorder/db_schema.py:663
Integration: Recorder
State attributes for sensor.f1_season_results exceed maximum size of 16384 bytes. This can cause database performance issues; Attributes will not be stored
```

The sensor can still display results in the frontend. If you use an older version without the automatic exclusion, or deliberately want to exclude the entire sensor from history, use this `recorder:` configuration:

```yaml
recorder:
  exclude:
    entities:
      - sensor.f1_season_results
```

</details>

## Related references

<span id="next-steps"></span>

<RelatedReferences id="season-results" />

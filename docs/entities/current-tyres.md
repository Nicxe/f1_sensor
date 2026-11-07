---
id: current-tyres
title: "Current Tyres"
description: "Current tyre compound, tyre age and known stint history per driver for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

See the tyre compound currently fitted to each driver’s car, its age and the known stint history for the session.

<EntityMeta id="current-tyres" />

<span id="state-and-attributes"></span>

Shows the current tyre compound for each driver in the active session.

## State

- Integer: number of drivers with tyre information available.

**Example**
```text
20
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| drivers | list | List of driver tyre information, sorted by car number |
| lap_current | number or null | Current reported session lap |
| lap_total | number or null | Scheduled session laps, when provided by the source |

### `drivers` entries

| Field | Type | Description |
| --- | --- | --- |
| racing_number | string | Car number |
| tla | string | Three-letter abbreviation (driver code) |
| team_color | string | Team color as hex code (e.g., "#3671C6") |
| team_color_rgb | list | Team color as RGB values (e.g., `[54, 113, 198]`) |
| position | string | Current position in the session |
| compound | string | Tyre compound name (e.g., "SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET") |
| compound_short | string | Single-letter abbreviation ("S", "M", "H", "I", "W") |
| compound_color | string | Hex color code for the compound (e.g., "#FF0000" for soft) |
| compound_color_rgb | list | Compound color as RGB values (e.g., `[255, 0, 0]` for soft) |
| new | boolean or null | Whether the current set was new when fitted; `null` means unknown |
| stint_laps | number or null | Reported total age of the current set, including laps driven before it was fitted |
| completed_laps | number or null | Driver's reported number of completed session laps |
| retired | boolean or null | Whether the driver is reported retired; `null` means unknown |
| in_pit | boolean or null | Whether the driver is currently reported in the pit lane; `null` means unknown |
| stint_history_complete | boolean | Whether the available stint history covers the driver from the start of the session |
| stints | list | Known tyre stints in chronological order; see the fields below |

### `stints` entries

| Field | Type | Description |
| --- | --- | --- |
| stint_index | number | Source stint identifier; it is not a pit-stop count |
| compound | string or null | Tyre compound for this stint |
| new | boolean or null | Whether the set was new when fitted |
| first_lap | number or null | First session lap assigned to the stint, when known |
| last_lap | number or null | Last completed session lap assigned to the stint, when known |
| stint_laps | number or null | Laps driven in this stint, excluding mileage before fitting |
| tyre_age_at_start | number or null | Laps already on the set when fitted; zero and unknown are different |
| total_laps | number or null | Reported total tyre age; final age for a completed stint, latest age for the current stint |
| is_current | boolean | Whether this is the latest fitted set; it can remain `true` after retirement or session end |
| coverage | string | `complete` or `partial`, describing whether the stint's lap boundaries and age are known |

The driver's top-level `stint_laps` retains its existing meaning: total age of the current tyres. The nested `stints[].stint_laps` is the distance driven during one stint. For example, a set fitted with three earlier laps and then driven for fourteen laps has `tyre_age_at_start: 3`, `stint_laps: 14` and `total_laps: 17`. Do not add the start age to `total_laps` again.

The [Tyres history view](/cards/modular#show-tyre-history) keeps completed stints visible and shows their total age at the time of the tyre change. A source update that continues the same set is not shown as a new tyre change.

:::info
History belongs to the selected session and may be incomplete after a late connection, an integration restart or an incomplete source snapshot. Unknown numeric fields remain `null` and appear as **—** in the card. A reported zero remains zero; missing data does not establish that tyres were new.
:::

## Examples

<details>
<summary>JSON Structure Example</summary>

```json
{
  "drivers": [
    {
      "racing_number": "1",
      "tla": "VER",
      "team_color": "#3671C6",
      "team_color_rgb": [54, 113, 198],
      "position": "1",
      "compound": "MEDIUM",
      "compound_short": "M",
      "compound_color": "#FFFF00",
      "compound_color_rgb": [255, 255, 0],
      "new": false,
      "stint_laps": 15
    },
    {
      "racing_number": "44",
      "tla": "HAM",
      "team_color": "#ED1131",
      "team_color_rgb": [237, 17, 49],
      "position": "2",
      "compound": "HARD",
      "compound_short": "H",
      "compound_color": "#FFFFFF",
      "compound_color_rgb": [255, 255, 255],
      "new": true,
      "stint_laps": 3
    },
    {
      "racing_number": "4",
      "tla": "NOR",
      "team_color": "#FF8000",
      "team_color_rgb": [255, 128, 0],
      "position": "3",
      "compound": "SOFT",
      "compound_short": "S",
      "compound_color": "#FF0000",
      "compound_color_rgb": [255, 0, 0],
      "new": true,
      "stint_laps": 1
    }
  ]
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get a driver's current tyre:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') or [] %}
{% set ver = drivers | selectattr('tla', 'eq', 'VER') | first | default(none) %}
{% if ver %}
  VER on {{ ver.compound }} ({{ ver.stint_laps }} laps{% if ver.new %}, NEW{% endif %})
{% endif %}
```

**Count drivers on each compound:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') or [] %}
{% if drivers %}
  SOFT: {{ drivers | selectattr('compound', 'eq', 'SOFT') | list | length }}
  MEDIUM: {{ drivers | selectattr('compound', 'eq', 'MEDIUM') | list | length }}
  HARD: {{ drivers | selectattr('compound', 'eq', 'HARD') | list | length }}
{% endif %}
```

**List drivers whose current set was fitted new:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') or [] %}
{% for d in drivers if d.new %}
  {{ d.tla }} - {{ d.compound }}, fitted new
{% endfor %}
```

**Find the oldest current tyre set:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') or [] %}
{% if drivers %}
  {% set longest = drivers | sort(attribute='stint_laps', reverse=true) | first | default(none) %}
  {{ longest.tla }} has {{ longest.stint_laps }} laps on {{ longest.compound }}
{% endif %}
```

**Create a tyre summary in position order:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') or [] %}
{% set ranked = namespace(rows=[]) %}
{% for driver in drivers %}
  {% set position = driver.position | int(999) %}
  {% set ranked.rows = ranked.rows + [{'position': position, 'driver': driver}] %}
{% endfor %}
{% for row in ranked.rows | sort(attribute='position') %}
  {% set d = row.driver %}
  P{{ d.position }} {{ d.tla }}: {{ d.compound_short }} ({{ d.stint_laps }} laps)
{% endfor %}
```

</details>

## Related references

<span id="next-steps"></span>

<RelatedReferences id="current-tyres" />

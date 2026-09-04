---
id: driver-standings
title: "Driver Standings"
description: "Current driver championship standings \u2014 state, attributes, and examples for F1 Sensor."
---

Current driver championship standings. Use `sensor.f1_driver_standings` in dashboards, templates, and automations.

This reference covers the state and attributes. For setup, see [Configuration](/getting-started/add-integration).

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`sensor.f1_driver_standings` - Driver standings snapshot from Ergast.

**State**

- Integer: number of drivers in the standings list.

**Example**
```text
20
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| round | string | Round of the standings snapshot |
| driver_standings | list | Ergast "DriverStandings" array |

Each entry in `driver_standings` contains:

| Field | Type | Description |
| --- | --- | --- |
| position | string | Championship position |
| positionText | string | Position as display text |
| points | string | Total points |
| wins | string | Number of wins |
| Driver | object | Driver information |
| Constructors | list | List of constructor(s) the driver has raced for |

The `Driver` object contains:

| Field | Type | Description |
| --- | --- | --- |
| driverId | string | Driver identifier (e.g., "max_verstappen") |
| permanentNumber | string | Permanent car number |
| code | string | Three-letter driver code (TLA) |
| url | string | Wikipedia URL |
| givenName | string | First name |
| familyName | string | Last name |
| dateOfBirth | string | Date of birth (YYYY-MM-DD) |
| nationality | string | Nationality |

Each entry in `Constructors` contains:

| Field | Type | Description |
| --- | --- | --- |
| constructorId | string | Constructor identifier |
| url | string | Wikipedia URL |
| name | string | Team name |
| nationality | string | Team nationality |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "season": "2025",
  "round": "12",
  "driver_standings": [
    {
      "position": "1",
      "positionText": "1",
      "points": "255",
      "wins": "7",
      "Driver": {
        "driverId": "max_verstappen",
        "permanentNumber": "1",
        "code": "VER",
        "url": "http://en.wikipedia.org/wiki/Max_Verstappen",
        "givenName": "Max",
        "familyName": "Verstappen",
        "dateOfBirth": "1997-09-30",
        "nationality": "Dutch"
      },
      "Constructors": [
        {
          "constructorId": "red_bull",
          "url": "http://en.wikipedia.org/wiki/Red_Bull_Racing",
          "name": "Red Bull",
          "nationality": "Austrian"
        }
      ]
    },
    {
      "position": "2",
      "positionText": "2",
      "points": "180",
      "wins": "2",
      "Driver": {
        "driverId": "lewis_hamilton",
        "permanentNumber": "44",
        "code": "HAM",
        "url": "http://en.wikipedia.org/wiki/Lewis_Hamilton",
        "givenName": "Lewis",
        "familyName": "Hamilton",
        "dateOfBirth": "1985-01-07",
        "nationality": "British"
      },
      "Constructors": [
        {
          "constructorId": "ferrari",
          "url": "http://en.wikipedia.org/wiki/Scuderia_Ferrari",
          "name": "Ferrari",
          "nationality": "Italian"
        }
      ]
    }
  ]
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get championship leader:**
```jinja2
{% set standings = state_attr('sensor.f1_driver_standings', 'driver_standings') %}
{% if standings and standings | length > 0 %}
  {% set leader = standings[0] %}
  Leader: {{ leader.Driver.givenName }} {{ leader.Driver.familyName }} ({{ leader.points }} pts)
{% endif %}
```

**Get a specific driver's position:**
```jinja2
{% set standings = state_attr('sensor.f1_driver_standings', 'driver_standings') %}
{% set ver = standings | selectattr('Driver.code', 'eq', 'VER') | first %}
{% if ver %}
  VER is P{{ ver.position }} with {{ ver.points }} points and {{ ver.wins }} wins
{% endif %}
```

**Calculate points gap to leader:**
```jinja2
{% set standings = state_attr('sensor.f1_driver_standings', 'driver_standings') %}
{% if standings and standings | length > 1 %}
  {% set leader_pts = standings[0].points | int %}
  {% set second_pts = standings[1].points | int %}
  Gap: {{ leader_pts - second_pts }} points
{% endif %}
```

**List top 5 drivers:**
```jinja2
{% set standings = state_attr('sensor.f1_driver_standings', 'driver_standings') %}
{% for d in standings[:5] %}
  P{{ d.position }}: {{ d.Driver.code }} - {{ d.points }} pts
{% endfor %}
```

**Get driver by car number:**
```jinja2
{% set standings = state_attr('sensor.f1_driver_standings', 'driver_standings') %}
{% set driver = standings | selectattr('Driver.permanentNumber', 'eq', '44') | first %}
{% if driver %}
  #44 {{ driver.Driver.familyName }} is P{{ driver.position }}
{% endif %}
```

</details>


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)

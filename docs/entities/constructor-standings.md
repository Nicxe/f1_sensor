---
id: constructor-standings
title: "Constructor Standings"
description: "Current constructor standings \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Current constructor standings.

<EntityMeta id="constructor-standings" />

<span id="state-and-attributes"></span>

`sensor.f1_constructor_standings` - Constructor standings snapshot from Jolpica's Ergast-compatible API.

## State

- Integer: number of constructors in the standings list.

**Example**
```text
10
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| round | string | Round of the standings snapshot |
| constructor_standings | list | Ergast “ConstructorStandings” array (positions, points, wins, constructor info) |

### `constructor_standings` entries

The integration passes through the upstream Ergast-compatible standings records. The usual fields are:

| Field | Type | Description |
| --- | --- | --- |
| position | string | Championship position |
| positionText | string | Position as display text |
| points | string | Championship points |
| wins | string | Wins |
| Constructor | object | Constructor identity |

### `Constructor` object

| Field | Type | Description |
| --- | --- | --- |
| constructorId | string | Constructor identifier |
| url | string | External constructor information URL |
| name | string | Constructor name |
| nationality | string | Constructor nationality |

Fields depend on what the upstream record supplies. Use the `constructor_standings` list when you need the full record; the sensor state is only its item count.

## Related references

<span id="next-steps"></span>

<RelatedReferences id="constructor-standings" />

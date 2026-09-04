---
id: fia-decision-documents
title: "FIA Decision Documents"
description: "FIA decisions and documents for the current weekend \u2014 state, attributes, and examples for F1 Sensor."
---

FIA decisions and documents for the current weekend. Use `sensor.f1_fia_documents` in dashboards, templates, and automations.

This reference covers the state and attributes. For setup, see [Configuration](/getting-started/add-integration).

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

:::warning[BETA]
This sensor is in BETA. Data structure and availability may change as the upstream feed and parsing are refined.
:::

Collects FIA decisions and official documents for the current race weekend.

**State**
- Integer: latest document number (e.g., 27 for "Doc 27"), or `0` when none are available.

**Example**
```text
27
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| name | string | Document title (e.g., "Doc 27 - Penalty Decision") |
| url | string | URL to the FIA document |
| published | string | ISO‑8601 timestamp when the document was published |
| documents | list | Rolling list of up to 100 documents for the current weekend |
| race | object | Compact race context for the document set |

Each entry in `documents` contains:

| Field | Type | Description |
| --- | --- | --- |
| name | string | Document title |
| url | string | URL to the FIA document |
| published | string | ISO-8601 timestamp when available |
| document_number | number | FIA document number when it can be parsed from the title |

The `race` object contains:

| Field | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| round | string | Round number |
| race_name | string | Grand Prix name |
| race_date | string | Race date |
| race_time | string | Race start time |
| circuit_name | string | Circuit name |
| locality | string | Circuit locality |
| country | string | Circuit country |

The sensor maintains a history of up to 100 documents. When a new race weekend starts, detected by FIA "Document 1", the history is reset. The state prefers the highest parsed FIA document number so the sensor does not move backwards when the FIA page publishes older or incomplete metadata.


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)

---
id: minisectors
title: Add minisector status
description: Show source status for small track segments beside sector times or in a dedicated Minisectors module.
toc_max_heading_level: 3
---

Minisectors show status blocks, not a time for each segment. Add **Minisectors** to the [F1 Sensor card](/cards/modular), or select the combined sector fields in a **Timing** module.

## Choose a presentation

Minisectors show the status published for each small segment of S1, S2 and S3.
The source does not publish a time for each minisector, so the card does not
calculate or estimate one.

Choose the presentation that fits each module:

| Presentation | Fields to select |
| --- | --- |
| Sector time only | **S1**, **S2** and **S3** in Timing. |
| Sector time with status blocks | **S1 with minisectors**, **S2 with minisectors** and **S3 with minisectors**. |
| Status blocks only | **S1 minisectors**, **S2 minisectors** and **S3 minisectors**, either in Timing or in a separate **Minisectors** module. |

These are ordinary optional fields. You can reorder them, combine them with other
fields and configure each Timing or Minisectors module independently. The separate
Minisectors module starts with Driver and the three status strips. No existing
Timing profile adds minisectors automatically.

Status strips are available for live and replay practice, qualifying, sprint
qualifying, sprint and race sessions when the source has supplied segment data.
Different circuits can have different numbers of blocks. Before the first segment
frame, or when a selected archive has no segment data, the module follows its
**When data is unavailable** setting. Ordinary sector timing remains available
when only minisector data is unavailable.


## Interpret colors and shapes

The blocks use the same purple diamond, green circle and yellow square as other timing status. Yellow means a recorded source status; it does not prove a slower segment than the preceding lap. Missing and unrecognized states remain neutral. Enable the module's status legend to keep this explanation beside the data.

For the complete timing legend and short-lived card-data behavior, see [timing colors and symbols](/cards/timing#read-timing-colors-and-symbols).

## Continue

- [Choose timing columns and driver details](/cards/timing)
- [Improve contrast and keyboard access](/cards/modular-accessibility)
- [Understand automatic card data](/features/card-data-and-sensors)

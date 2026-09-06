---
id: session-archive
title: Session Archive compatibility
description: Keep an existing Session Archive card working or move it to the Results card's Archive view.
---

The earlier `custom:f1-session-archive-card` type opened historical results. That view is now included in [Results](/cards/results). Existing Session Archive configurations still work, but new dashboards should add **F1 Results** from the card picker.

## Keep an existing card

You do not need to replace the old type immediately. It opens Results with Archive enabled and selected. Your custom title is kept; the old default title **F1 Session Archive** gives way to the Results card's session title.

The old type is a compatibility entry, not an additional selectable card or a separate download. Its display and data limits are the same as [Results Archive](/features/historical-results).

## Update the YAML

Edit the existing card and use the current type with Archive as its default view:

```yaml
type: custom:f1-last-race-results-card
default_scope: archive
show_archive: true
history_year: 2024
history_entry_id: auto
theme_mode: auto
```

Preserve any explicit source selections or display options from your old card.

| Old setting | Current setting | Behavior |
| --- | --- | --- |
| `type: custom:f1-session-archive-card` | `type: custom:f1-last-race-results-card` | Use the current Results card. |
| `year` | `history_year` | Initial Archive season. The current name takes priority when both are present. |
| `entry_id` | `history_entry_id` | Integration entry used for historical requests. Keep your explicit entry if you have several. |
| Archive-only opening | `default_scope: archive` and `show_archive: true` | Start in Archive while retaining the Results card's navigation. |

## If the card is missing

If the card is missing after an update, check that the [bundled card resource is current](/cards/installation#card-loading-checks). Do not add a second resource for Session Archive.

## Related

- [Browse historical results](/features/historical-results)
- [Results configuration](/cards/results#configuration)
- [All dashboard cards](/cards/cards-overview)

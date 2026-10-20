---
id: card-data-api
title: Card data protocol
description: Entry-scoped discovery, versioned direct-data subscriptions, protection rules and lifecycle guarantees for F1 Sensor card clients.
---

This reference describes the modular card's direct data transport. Sensor states and attributes remain available when their entities are selected. [Card data](/features/card-data-and-sensors) is automatic and independent of sensor exposure. Module subscriptions acquire the shared data sources they need.

## Discover support

Send `f1_sensor/entities` through Home Assistant's authenticated WebSocket API. Each entry includes its existing entity mappings and additive `data_api` metadata: `protocol_version`, `supported`, `enabled`, `automatic`, `race_control_event` and `configuration_required`. Current backends set `automatic: true`, list all supported generic areas in `enabled` and set `configuration_required: false`. Availability is reported separately for each data area; advertising a dataset does not grant live or authenticated access.

A client on an older backend without `data_api` uses existing entity discovery. A client with direct support chooses transport per data area. An error, protection block or missing response from an advertised direct transport does not authorize silent fallback to entity attributes.

## Subscribe

```json
{
  "id": 10,
  "type": "f1_sensor/data/subscribe",
  "entry_id": "YOUR_CONFIG_ENTRY_ID",
  "protocol_version": 1,
  "data_keys": ["driver_standings", "constructor_standings"]
}
```

The command acknowledges the subscription, sends its own initial snapshot for every requested area, then sends changed requested areas. There is no separate initial GET. Unsubscribe using Home Assistant's standard `unsubscribe_events` command. Unknown entries, unsupported areas, unloaded runtime return explicit errors. There is no upgrade-acknowledgement error in the automatic backend.

## Read envelopes

Every snapshot includes `protocol_version`, `entry_id`, `dataset`, `source`, `context`, `generation`, `revision`, `status`, `reason`, `timestamps` and `payload`. `payload` contains processed `state` and `attributes`. Status is `ready`, `stale`, `loading`, `unavailable`, `blocked`, `unsupported` or `closed`.

Source is `static`, `live` or `replay`. Live context identifies the session, replay generation, live delay and qualifying part. Qualifying context arrives immediately; clients hide timing from an earlier part until its matching update arrives. No Spoiler Mode hides the part metadata while protection is active. Static context includes known season and round. Timestamps distinguish known observation time from receipt time; unknown observation time is `null`. Clients must not label receipt time as source freshness.

A generation retires earlier work after reload, session changes or replay rebuilds. Revision orders changes within the generation. Clients discard older revisions and retired generations, and stop using data after `closed`. Do not combine live areas from different generations.

Static areas publish on change. General live data is limited to one publication per second per area. Context and protection changes are delivered immediately. No Spoiler Mode and Live Delay apply to initial snapshots, caches and reconnects as well as later updates.

## Shared ownership and special transports

Runtime owns neutral calculation models, coordinator listeners, persisted session accumulators and time-dependent updates. Existing providers, HTTP caches, storage and the shared LiveBus perform collection. No hidden sensor entities are created for card data. Multiple clients share each data area and underlying coordinator demand; removing the final client releases its on-demand listeners. Necessary incremental history retains background demand within existing session windows when live timing is enabled. Static sources warm lazily, with parent sources ready before derived forecasts, documents or circuit history. Closing a card releases on-demand polling and dependency listeners; an active sensor retains its own demand.

Automatic backends advertise `race_control_event: "f1_sensor_race_control_data"` for entry-addressed live log updates. This card channel does not opt an installation into public automation events. Public `f1_sensor_race_control_event` delivery retains its previous sensor/legacy demand. Older backends without this field use the existing event path.

Map, analysis, minisectors, archive and telemetry retain their specialized APIs. Race Control log reads and the `clear_race_control_log` action accept `entry_id` for sensor-free use, or the existing `entity_id`. Supply one address.

## Upgrade metadata

Config-entry schema 4.4 preserves sensor configuration and does not require an upgrade choice. `card_data_notice_version` in entry data records that one-time information was shown. It never controls operation. New installations start with this information already acknowledged.

Old `card_data_features` and `data_choice_version` values are retained as inert metadata when present; neither restricts card access nor blocks setup. `exposed_sensor_keys`, when present, remains the authoritative sensor allowlist. Existing legacy sensor-selection semantics are preserved when that allowlist is absent. Voluntary sensor reductions require review before registry entries are removed.

Older backends without `data_api` use the entity path. Older direct backends can still advertise restricted data or `configuration_required`; clients keep their existing fail-closed handling for those versions. New backend operation does not depend on that legacy state.

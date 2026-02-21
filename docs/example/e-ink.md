---
id: e-ink
title: E-ink Display
---

# E-ink Display — F1 Pit Wall

A dedicated F1 schedule display built with ESPHome and an e-ink screen. It pulls data directly from the F1 Sensor integration and shows the upcoming race weekend — circuit, date, session times — in a clean, always-on format that works without a running screen or dashboard.

This is a separate project maintained alongside F1 Sensor and is available as a ready-to-use ESPHome configuration.

:::info Project repository
Full source, wiring instructions, and configuration files are available at:
**[github.com/Nicxe/esphome](https://github.com/Nicxe/esphome)**
:::

![F1 Pit Wall e-ink display](/img/F1_pitwall.png)

---

## What it shows

The display is laid out as a compact race schedule overview:

- **Next race** — circuit name, country flag, round number, and race start time in local time
- **Upcoming sessions** — qualifying, practice, and sprint times for the current race weekend
- **Following races** — the next three rounds at a glance

All data comes from the `sensor.f1_race_next_race` and `sensor.f1_current_season` entities provided by F1 Sensor.

---

## What you need

- An ESP32 or ESP8266 board with an e-ink display (waveshare or similar)
- [ESPHome](https://esphome.io) installed
- F1 Sensor integration installed and configured with the next race and season sensors enabled
- Home Assistant with the ESPHome integration

---

## Getting started

1. Go to **[github.com/Nicxe/esphome](https://github.com/Nicxe/esphome)** and find the F1 display configuration
2. Follow the hardware setup and wiring guide in the repository
3. Flash the ESPHome configuration to your device
4. The display will connect to Home Assistant and start pulling data from F1 Sensor automatically

:::tip
The display updates on a schedule and on demand when sensor data changes. Since e-ink displays retain their image without power, the race schedule stays visible even when the ESP is in deep sleep — making it very power-efficient.
:::

---

## Related

- [Next Race sensor](/entities/static-data#next-race) — the primary data source for the display
- [Season Calendar](/entities/static-data#season-calendar) — for full session schedule data
- [Live Data Cards](/cards/cards-overview) — for live in-session dashboards

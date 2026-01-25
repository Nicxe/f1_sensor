---
id: live-delay
title: Live Delay, Sync with TV
---

The live update delay lets you delay delivery of live messages so they better align with what you see on TV or streaming services.

This is especially useful for dashboards and automations, for example flashing lights on a red flag or reacting to safety car deployments, so they happen at the same moment you see them on screen.

### Typical broadcast delays

Actual delays vary by provider, but these ranges are common:

• **Broadcast TV** (satellite, cable, terrestrial): ~5–10 seconds behind
• **Streaming services**: ~20–45 seconds behind, sometimes more
• **Sports cable / OTT providers**: ~45–60 seconds or more depending on provider

By setting the delay accordingly, Home Assistant can react in sync with the live pictures you are watching.

---


## Option 1 - Manual delay adjustment

At its core, Live Delay is a single value, stored in `number.f1_live_delay`

Changing this value **directly updates** the Live Delay Controller and delays all live messages. This value represents how many seconds the live data stream should be delayed before it is exposed to sensors.

Everything else in the integration builds on top of this number.

![Manual Live Delay](/img/live_delay_manual.png)

This method is simple and reliable. The guided calibration below is optional.

  ::::tip
  During the broadcast, they always show the moment the race clock flips to the start time, for example 15:00:00. If you look up an [atomic clock online](https://time.is/), you'll have an exact reference. Watch the time when the broadcast clock hits the start. So when the broadcast clock shows 15:00:00 and the formation lap starts, the atomic clock reads 15:00:30. Then set a 30-second delay in the configuration.
  ::::


---


## Option 2 - Guided calibration


The guided workflow helps you measure the delay automatically.

It uses these helper entities:

| Entity | Purpose |
| --- | --- |
| `switch.f1_delay_calibration` | Arm calibration and start the timer |
| `button.f1_match_live_delay` | Press when TV catches up to commit the delay |
| `select.f1_live_delay_reference` | Choose when the timer starts |

![Manual Live Auto](/img/live_delay_auto.png)

### Choose the calibration reference

Use `select.f1_live_delay_reference` to choose when the calibration timer starts:

- **Session live** - Timer starts at lights out (races) or pit exit open (practice/qualifying). This is the most precise option.
- **Formation start (race/sprint)** - Timer starts when the formation lap begins. This lets you focus on watching the start rather than pressing a button at lights out.

:::tip Formation start for races
For races and sprints, formation start is often the better choice. The timer starts automatically when the formation lap begins, so you only need to press the button when you see the formation lap start on TV. Then you can sit back and enjoy the actual race start.
:::

:::info Formation lap timing
The formation lap start point is estimated with approximately one second accuracy. The live data stream does not provide an exact marker for when the formation lap begins, so there may be a small offset.
:::

### Step 1 - Arm the calibration

Turn the switch `switch.f1_delay_calibration` **on** to start calibration mode.

What happens next depends on the chosen reference:

**Session live reference:**
- If the session is not live yet, the integration waits
- When lights go out (race) or pit exit opens (practice/qualifying), the timer starts automatically
- If the session is already live, timing starts immediately

**Formation start reference (race/sprint):**
- The integration waits for the formation lap marker
- When the formation lap begins, the timer starts automatically
- For practice and qualifying, it falls back to session live behavior

### Step 2 - Match the TV broadcast

When you see the reference point on your TV, press `button.f1_match_live_delay`. The elapsed time is measured and the result is written to `number.f1_live_delay`.

**With session live reference:** Press when you see lights out (race) or pit exit open (practice/qualifying).

**With formation start reference:** Press when you see the formation lap begin on TV.

:::info When does the session go live?

**Practice & Qualifying**
The session starts when the pit exit turns green. F1 TV usually shows a countdown to this moment.

**Qualifying**
Calibration is only needed for the start of **Q1**.

**Race (session live)**
The session starts when all five lights go out and the race begins. This is **not** the formation lap.

**Race (formation start)**
The timer starts when cars begin the formation lap, before the actual race start.
::::

---

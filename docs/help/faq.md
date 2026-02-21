---
id: faq
title: FAQ
---

# Frequently Asked Questions

[![Home Assistant Community Forum](https://img.shields.io/badge/Home%20Assistant-Community%20Forum-319fee?logo=home-assistant)](https://community.home-assistant.io/t/formula-1-racing-sensor/880842) [![GitHub Issues](https://img.shields.io/badge/GitHub-Issues-181717?logo=github)](https://github.com/Nicxe/f1_sensor/issues)

### General Questions




<details>
<summary>Do I need to configure any API keys or separate weather API for F1 Sensor?</summary>

No, the integration does not require any API keys. All data is fetched automatically from the provided APIs. You just install and add the integration, no additional API setup is needed.
</details>


<details>
<summary>Can I use the F1 Sensor data in ESPHome directly (for example, on an ESP32 display)?</summary>

Not directly. F1 Sensor is a Home Assistant integration (running on Home Assistant), not an ESPHome component. This means ESPHome devices can’t retrieve F1 data on their own from this integration. 

The workaround is to have Home Assistant pass the data to the ESPHome device, for instance, by using the Home Assistant API or MQTT to send sensor values to your ESPHome device. 


In summary, the F1 sensors live in Home Assistant, you can mirror those entity states to ESPHome, but you cannot import the integration into ESPHome itself.
</details>


<details>
<summary>Are practice and qualifying session times available in F1 Sensor?</summary>

The integration does not create separate sensors for each practice or qualifying session by default (only for the race and overall “next race” info). 

However, the schedule information for practice sessions and qualifying is included in the data. For example, the `sensor.f1_next_race` (next race info) or the season calendar sensor contains the timings for all sessions of the Grand Prix weekend. 

You can use those attributes in templates or in the calendar to know when FP1, FP2, FP3, Quali, etc., occur. There is currently no dedicated “FP1 sensor” or “qualifying sensor” – this has been requested as a feature, but for now you’ll use the provided schedule data from the existing sensors.
</details>


### Live Data Questions



<details>
<summary>Why are the live sensors (e.g. track status, session status) not updating outside of race sessions?</summary>

This is expected behavior. The live sensors only update shortly before, during, and just after an active session (practice, qualifying, sprint, or race). Outside of those times, they will not update and may appear static. In other words, you’ll only see changes in those sensors when a Formula 1 session is happening or about to happen.
</details>


<details>
<summary>Will the live data work if I watch a race replay later (not live)?</summary>

Yes! The integration includes [**Replay Mode**](/features/replay-mode) which lets you play back historical sessions with full Home Assistant integration. When you watch a recorded race from F1 TV or another service, you can sync all your automations and dashboards to work exactly as they would during a live broadcast.

See the [Replay Mode documentation](/features/replay-mode) for setup instructions.
</details>


<details>
<summary>How do I adjust the live update delay to sync with my broadcast? Where is that setting?</summary>

The integration provides multiple ways to adjust the live delay:

1. **Direct adjustment**: Change `number.f1_system_live_delay` to set the delay in seconds
2. **Guided calibration**: Use the built-in calibration workflow with `switch.f1_system_delay_calibration`

For detailed instructions including automatic calibration during a live session, see [**Live Delay**](/features/live-delay).
</details>



<details>
<summary>Where can I find the Race Control messages (like flag notices, safety car deploy messages)?</summary>

Race Control messages are available in two ways:

1. **Sensor**: `sensor.f1_race_control` shows the latest message and maintains a history. See [Race Control](/entities/live-data#race-control) for details.

2. **Events**: Messages are also emitted as `f1_sensor_race_control_event` events for automation triggers. See [Events](/entities/events) for the event format.

For example automations, check the [Automation](/automation) page.
</details>



<details>
<summary>How can I tell which session is currently live (Practice, Qualifying, Race, etc.)?</summary>

As of version 2.2.0, there is a sensor for this. The integration provides `sensor.f1_current_session` which indicates the name of the session that is currently running. 

For example, it will show values like “Practice 1”, “Qualifying”, “Sprint Shootout”, or “Race” when those sessions are in progress. This complements the `f1_session_session_status` sensor (which shows the state like pre/live/finished) by telling you exactly which session is active. 

This is useful for automations or dashboards that need to behave differently for practice vs. race, etc.
</details>



<details>
<summary>Does the integration include live flag status and safety car information?</summary>

Yes. The F1 Sensor integration has live sensors for track flags and safety car status. The entity `sensor.f1_track_status` reflects the current track flag/status in real time (possible states include CLEAR, YELLOW, VSC, SC, RED, etc.). 

Additionally, `binary_sensor.f1_safety_car` turns on whenever a Safety Car or Virtual Safety Car is active on track. These live sensors let you react to yellow/red flags or safety car deployments in your Home Assistant automations (for example, changing lights to red on a red flag).
</details>






<details>
<summary>Can F1 Sensor show live driver positions or lap times like a Formula 1 timing tower?</summary>

Not at the moment. The integration focuses on key session data (session status, flags, laps, standings, etc.) rather than real-time timing for every driver. Live driver position tracking (essentially the running order with continuous updates) is quite complex and is not currently implemented. The developer has explored it, but handling that much real-time data reliably is challenging, so there’s no guarantee it will be added. Future updates may introduce more live data features (the roadmap includes ideas like enhanced live timing), but as of now there is no sensor for constantly updating driver positions during a session.
</details>


<details>
<summary>How can I display “Lap X of Y” for the current race?</summary>

The integration provides the current lap number as `sensor.f1_race_lap_count` during an active race. To get the total number of laps, use the sensor’s attributes. The `f1_session_race_lap_count` sensor has an attribute named `total_laps` that represents the total laps scheduled for the race. 

For example, if the sensor state is `12` and the `total_laps` attribute is `56`, you can construct a template or use a custom card to show “Lap 12 of 56.” 

*(If you see total_laps: unknown, it may mean the race info hasn’t fully synced yet or you’re checking outside of an active race. It should populate once the race session data is live.)*
</details>


### Troubleshooting

<details>
<summary>I updated F1 Sensor but I don’t see the new sensors (like track status or weather) – where are they?</summary>

You likely need to enable the new live data sensors in the integration’s config.

After updating to a version that introduces new sensors, open the F1 Sensor integration’s options (Reconfigure) and make sure “Enable live F1 API” or the relevant option is turned on. Once enabled and saved, the new sensors (e.g. session status, track status, etc.) will be created. 

::::info
This step is required because live data is off by default until you opt-in.*
::::
</details>

---

## Can't find the answer you're looking for?

If you're still having issues, head over to the [Contact](./contact) page.
# F1 Sensor for Home Assistant
![GitHub release (latest)](https://img.shields.io/github/v/release/Nicxe/f1_sensor)
![HACS Custom](https://img.shields.io/badge/HACS-Custom-blue)

## What is F1 Sensor?

This is a custom integration for Home Assistant that creates sensors using data from the [Jolpica-F1 API](https://github.com/jolpica/jolpica-f1). It is designed for users who want to build automations, scripts, notifications, TTS messages, or more advanced use cases such as generating dynamic dashboards, triggering race-day routines, syncing events to calendars, or integrating with external services based on upcoming Formula 1 events.

> [!TIP]
> If your goal is to visually display upcoming race information, current standings, and more in your Home Assistant dashboard, the [FormulaOne Card](https://github.com/marcokreeft87/formulaone-card) is the better choice for that purpose.

This integration **does not provide any UI components**. Instead, it creates:
- `sensor.f1_next_race` — Attributes include detailed information about the next race, such as when and where it takes place.
- `sensor.f1_season_calendar` — A list of all races in the current F1 season.
- `sensor.f1_driver_standings` — Current driver championship standings.
- `sensor.f1_constructor_standings` — Current constructor championship standings.
- `sensor.f1_weather`: Current weather and race-time forecast at the next race location.
- `sensor.f1_latest_race_results`: Results from the most recent Formula 1 race.
- `sensor.f1_season_results`: All race results for the ongoing season.
- `sensor.f1_race_week`: A native binary sensor that returns `on` if it's currently race week. *(new)*



### New Features
- Added `race_week` sensor: A native **binary sensor** that returns `on` if it's currently race week.
  - Includes attributes:
    - `days_until_next_race`
    - `next_race_name`
  - Useful for dynamically updating dashboards or automations around race weekends!


### How to Enable

To use these new sensor:
1. Go to **Settings > Devices & Services**, find the F1 integration.
2. Click the **three dots** → **Reconfigure**, and enable the new sensors by checking the boxes.

During installation, you can choose exactly which sensors you want to include in your setup.  
This gives you control over which data points to load — for example, only the next race and weather, without standings or calendar.

You can always change this selection later by reconfiguring the integration via **Settings > Devices & Services** in Home Assistant.

The integration fetches fresh data from the Jolpica-F1 API every 1 hours.

I personally use this integration to display the next race and the following three races on an e-ink display. You can read more about that setup [here](https://github.com/Nicxe/esphome).

---

### Known Issue

`sensor.f1_season_results` may trigger a warning in the Home Assistant logs:

```yaml
Logger: homeassistant.components.recorder.db_schema
Source: components/recorder/db_schema.py:663
Integration: Recorder
State attributes for sensor.f1_season_results exceed maximum size of 16384 bytes. This can cause database performance issues; Attributes will not be stored
```

Despite the warning, the sensor should still work fine for display in the frontend. However, to avoid any database load/performance issues, it is recommended to **exclude this sensor from being recorded** in your `recorder:` config:

```yaml
recorder:
  exclude:
    entities:
      - sensor.f1_season_results
```

---

## Installation

You can install this integration as a custom repository by following one of these guides:

### With HACS (Recommended)

To install the custom component using HACS:

1. Click on the three dots in the top right corner of the HACS overview menu.
2. Select **Custom repositories**.
3. Add the repository URL: `https://github.com/Nicxe/f1_sensor`.
4. Select type: **Integration**.
5. Click the **ADD** button.

<details>
<summary>Without HACS</summary>

1. Download the latest release of the F1 Sensor integration from **[GitHub Releases](https://github.com/Nicxe/f1_sensor/releases)**.
2. Extract the downloaded files and place the `f1_sensor` folder in your Home Assistant `custom_components` directory (usually located in the `config/custom_components` directory).
3. Restart your Home Assistant instance to load the new integration.

</details>

---

## Configuration

To add the integration to your Home Assistant instance, use the button below:

[![Open your Home Assistant instance and start configuration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=f1_sensor)

### Manual Configuration

If the button above does not work, you can also perform the following steps manually:

1. Browse to your Home Assistant instance.
2. Go to **Settings > Devices & Services**.
3. In the bottom right corner, select the **Add Integration** button.
4. From the list, select **F1 Sensor**.
5. Follow the on-screen instructions to complete the setup.

<br>

## Example

### E-ink display

This [e-ink display project](https://github.com/Nicxe/esphome) uses the sensors from this integration to show upcoming Formula 1 races, including race countdown and schedule.

![E-ink example](https://github.com/user-attachments/assets/96185a06-ed0b-421a-afa6-884864baca63)

---

### Custom F1 Card by the Community

Community user Tiidler has used the sensors from this integration to create a fully custom F1 dashboard card in Home Assistant, displaying race schedule, standings, podium results, and weather, all styled to fit their setup.

![image (1)](https://github.com/user-attachments/assets/4ed2748c-2ae7-4529-8767-bedbaa98636f)





---



### Announce next race and top standings via TTS

```yaml
service: tts.google_translate_say
data:
  entity_id: media_player.living_room_speaker
  message: >
    {% set next_race = state_attr('sensor.f1_next_race', 'race_name') %}
    {% set race_date = as_datetime(state_attr('sensor.f1_next_race', 'race_start')) %}
    {% set race_location = state_attr('sensor.f1_next_race', 'circuit_locality') %}
    {% set race_country = state_attr('sensor.f1_next_race', 'circuit_country') %}
    {% set days_left = (race_date.date() - now().date()).days %}
    {% set drivers = state_attr('sensor.f1_driver_standings', 'driver_standings') %}
    {% set constructors = state_attr('sensor.f1_constructor_standings', 'constructor_standings') %}
    The next Formula 1 race is the {{ next_race }} in {{ race_location }}, {{ race_country }}, happening in {{ days_left }} day{{ 's' if days_left != 1 else '' }}.
    The top 3 drivers right now are:
    Number 1: {{ drivers[0].Driver.givenName }} {{ drivers[0].Driver.familyName }} with {{ drivers[0].points }} points.
    Number 2: {{ drivers[1].Driver.givenName }} {{ drivers[1].Driver.familyName }} with {{ drivers[1].points }} points.
    Number 3: {{ drivers[2].Driver.givenName }} {{ drivers[2].Driver.familyName }} with {{ drivers[2].points }} points.
    In the constructor standings:
    Number 1: {{ constructors[0].Constructor.name }} with {{ constructors[0].points }} points.
    Number 2: {{ constructors[1].Constructor.name }} with {{ constructors[1].points }} points.
    Number 3: {{ constructors[2].Constructor.name }} with {{ constructors[2].points }} points.
```

---

### Mobile notification with race info and standings

```yaml
service: notify.mobile_app_yourdevice
data:
  title: "🏁 Formula 1 Update"
  message: >
    {% set race = state_attr('sensor.f1_next_race', 'race_name') %}
    {% set city = state_attr('sensor.f1_next_race', 'circuit_locality') %}
    {% set country = state_attr('sensor.f1_next_race', 'circuit_country') %}
    {% set race_time = as_datetime(state_attr('sensor.f1_next_race', 'race_start')) %}
    {% set days = (race_time.date() - now().date()).days %}
    {% set drivers = state_attr('sensor.f1_driver_standings', 'driver_standings') %}
    {% set constructors = state_attr('sensor.f1_constructor_standings', 'constructor_standings') %}
    Next race: {{ race }} in {{ city }}, {{ country }} — in {{ days }} day{{ 's' if days != 1 else '' }}.
    Top drivers:
    1. {{ drivers[0].Driver.familyName }} ({{ drivers[0].points }} pts)
    2. {{ drivers[1].Driver.familyName }} ({{ drivers[1].points }} pts)
    3. {{ drivers[2].Driver.familyName }} ({{ drivers[2].points }} pts)
    Top constructors:
    1. {{ constructors[0].Constructor.name }} ({{ constructors[0].points }} pts)
    2. {{ constructors[1].Constructor.name }} ({{ constructors[1].points }} pts)
    3. {{ constructors[2].Constructor.name }} ({{ constructors[2].points }} pts)
```

---

> [!NOTE]  
> ### Support the API that makes this possible  
> This integration relies entirely on the amazing [Jolpica-F1 API](https://github.com/jolpica/jolpica-f1), which provides high-quality and up-to-date Formula 1 data for free.  
> If you find this integration useful, please consider supporting the creator of the API by donating to their Ko-fi page: [https://ko-fi.com/jolpic](https://ko-fi.com/jolpic)  
> Without this API, this integration would not be possible, so any support helps keep it live and maintained. 🙏



## Contributing

Contributions, bug reports, and feedback are welcome. Please feel free to open issues or pull requests on GitHub.

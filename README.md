# F1 Sensor for Home Assistant

![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=) <img alt="Maintenance" src="https://img.shields.io/maintenance/yes/2025"> <img alt="GitHub last commit" src="https://img.shields.io/github/last-commit/Nicxe/f1_sensor"> <img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/Nicxe/f1_sensor">


### OVERVIEW

The F1 Sensor integration connects Home Assistant with the Jolpica–F1 API to bring Formula 1 data into your smart home. And by leveraging Formula 1’s unofficial Live Timing API, the integration provides real-time updates on flag status and Safety Car conditions throughout each race weekend.


> [!TIP]
Visit the [F1 Sensor Community at Home Assistant Community Forum](https://community.home-assistant.io/t/formula-1-racing-sensor/) to share your project and get help and inspiration.



### KEY FEATURES
- Lightweight, choose only the sensors you need  
- Real-time updates on flag and Safety Car status 
- Full timestamp support in UTC and local time  
- Current weather and forecast for the next race location, including expected conditions at race start
- Ideal for TTS, notifications, automations, and custom dashboards
- Automate your lights to flash red whenever a red flag is active during a session.
<br>

### INSTALLATION & CONFIGURATION

To install this integration as a custom repository, use the button below<br>
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Nicxe&repository=f1_sensor&category=integration)

then add the integration to your Home Assistant instance, use the button below<br>
[![Open your Home Assistant instance and start configuration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=f1_sensor)

<details>
<summary>Manual configuration steps</summary>

**Installation:**   
1. Download the latest release of the F1 Sensor integration from **[GitHub Releases](https://github.com/Nicxe/f1_sensor/releases)**.
2. Extract the downloaded files and place the `f1_sensor` folder in your Home Assistant `custom_components` directory (usually located in the `config/custom_components` directory).
3. Restart your Home Assistant instance to load the new integration.

**Configuration**
1. Browse to your Home Assistant instance.
2. Go to **Settings > Devices & Services**.
3. In the bottom right corner, select the **Add Integration** button.
4. From the list, select **F1 Sensor**.
5. Follow the on-screen instructions to complete the setup.
    
</details>
<br>

### OPTIONS
Select which sensors to enable during setup. You can always change this selection later by reconfiguring the integration via Settings > Devices & Services in Home Assistant.


### UPDATING DATA
Automatic hourly updates via Jolpica–F1 API and real-time updates on flag status and Safety Car conditions throughout each race weekend.




### SUPPORTED FUNCTIONALITY

#### ENTITIES


| Entity                    | Info                                                             | 
| --------                  | --------                                                         | 
| sensor.f1_next_race       | Next race info    | 
| sensor.f1_season_calendar       | Full race schedule    | 
| sensor.f1_driver_standings       | Current driver championship standings    | 
| sensor.f1_constructor_standings       | Current constructor standings    | 
| sensor.f1_weather       | Weather forecast at next race circuit    | 
| sensor.f1_last_race_results       | Most recent race results    | 
| sensor.f1_season_results       | All season race results    | 
| binary_sensor.f1_race_week       | `on` during race week    |
| sensor.f1_flag       | Track flag status (yellow red, VSC)    | 
| binary_sensor.f1_safety_car       | `on` when Safety Car is active    |

<br>

> [!TIP]
> If your goal is to visually display upcoming race information, current standings, and more in your Home Assistant dashboard, the [FormulaOne Card](https://github.com/marcokreeft87/formulaone-card) is the better choice for that purpose.

<br>

### ADDITIONAL TECHNICAL DETAILS 

##### Timezone
All race timestamps provided in UTC and as _local fields in the circuit’s timezone as an attribute to `sensor.f1_next_race`


##### Known issue
`sensor.f1_season_results` may trigger a warning in the Home Assistant logs:
```
Logger: homeassistant.components.recorder.db_schema
Source: components/recorder/db_schema.py:663
Integration: Recorder
State attributes for sensor.f1_season_results exceed maximum size of 16384 bytes. This can cause database performance issues; Attributes will not be stored
```

Exclude sensor.f1_season_results from recorder to prevent database performance issues
```
recorder:
  exclude:
    entities:
      - sensor.f1_season_results
```




<br>

### EXAMPLE

#### E-ink display

This [e-ink display project](https://github.com/Nicxe/esphome) uses the sensors from this integration to show upcoming Formula 1 races, including race countdown and schedule.

![E-ink example](https://github.com/user-attachments/assets/96185a06-ed0b-421a-afa6-884864baca63)



#### Custom F1 Card by the Community

Community user Tiidler has used the sensors from this integration to create a fully custom F1 dashboard card in Home Assistant, displaying race schedule, standings, podium results, and weather, all styled to fit their setup.

![image (1)](https://github.com/user-attachments/assets/4ed2748c-2ae7-4529-8767-bedbaa98636f)








#### Announce next race and top standings via TTS

```yaml
service: tts.google_translate_say
data:
  entity_id: media_player.living_room_speaker
  message: >
    {% set next_race = state_attr('sensor.f1_next_race', 'race_name') %}
    {% set race_date = as_datetime(state_attr('sensor.f1_next_race', 'race_start_local')) %}
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


#### Mobile notification with race info and standings

```yaml
service: notify.mobile_app_yourdevice
data:
  title: "🏁 Formula 1 Update"
  message: >
    {% set race = state_attr('sensor.f1_next_race', 'race_name') %}
    {% set city = state_attr('sensor.f1_next_race', 'circuit_locality') %}
    {% set country = state_attr('sensor.f1_next_race', 'circuit_country') %}
    {% set race_time = as_datetime(state_attr('sensor.f1_next_race', 'race_start_local')) %}
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


<br>
<br>


### SUPPORTING THE PROJECT
If you want to support the continuous development of F1 Sensor, you can buy me a coffee<br>
<a href="https://buymeacoffee.com/niklasv" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: auto !important;width: auto !important;" ></a>
<br>

> [!NOTE]  
> Help me improve my documentation Suggest an edit to this page, or provide/view feedback for this page.





---
### Disclaimer
F1 Sensor is an unofficial integration and has no affiliation with Formula 1 or any of its companies. All trademarks, including F1, FORMULA ONE, FORMULA 1, FIA FORMULA ONE WORLD CHAMPIONSHIP, GRAND PRIX, and related names, are the property of Formula One Licensing B.V.

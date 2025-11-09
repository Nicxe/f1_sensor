---
id: season-progression-charts
title: Season Progression Charts
---


These two charts visualize the season progression for both the Drivers’ Championship and the Constructors’ Championship.
They rely on data from the sensors `sensor.f1_driver_standings` and `sensor.f1_constructor_standings`.

<img width="695,5" height="475" alt="image" src="https://github.com/user-attachments/assets/e1a7202c-13c0-49dd-9c5b-0ecbf5b71d73" />
<img width="691,5" height="471" alt="image" src="https://github.com/user-attachments/assets/54867035-c183-49c6-b03f-61cd396adb2e" />



To use these examples, make sure you have the following custom cards installed in Home Assistant:
- [F1 Sensor](https://github.com/Nicxe/f1_sensor) integration version 2.3.0 or later
- [auto-entities](https://github.com/thomasloven/lovelace-auto-entities)
- [ApexCharts Card](https://github.com/RomRider/apexcharts-card)

Once installed, you can add the provided YAML configuration to your dashboard to display the charts.

#### Drivers Progression Chart
```yaml
type: custom:auto-entities
card_param: series
show_empty: false
card:
  type: custom:apexcharts-card
  header:
    show: true
    title: Season progression - drivers points
    show_states: false
  apex_config:
    chart:
      animations:
        enabled: false
    markers:
      size: 6
      strokeWidth: 2
      hover:
        sizeOffset: 8
    states:
      hover:
        filter:
          type: darken
          value: 0.45
      active:
        allowMultipleDataPointsSelection: false
        filter:
          type: darken
          value: 0.55
    legend:
      show: true
      position: left
      horizontalAlign: left
      itemMargin:
        vertical: 4
      fontSize: 12px
    xaxis:
      type: category
      tickPlacement: between
      labels:
        rotate: -35
        trim: false
        minHeight: 60
    tooltip:
      shared: false
      intersect: true
      x:
        formatter: |
          EVAL:function (val) { return val; }
      "y":
        formatter: |
          EVAL:function (val) { return Math.round(val); }
filter:
  template: >
    {%- set e = 'sensor.f1_driver_points_progression' -%} {%- set drivers =
    state_attr(e, 'drivers') or {} -%} {%- set palette = {
      'VER':'#4781D7','PER':'#6C98FF','NOR':'#F47600','PIA':'#F47600',
      'LEC':'#ED1131','SAI':'#1868DB','HAM':'#ED1131','RUS':'#00D7B6',
      'ALO':'#229971','STR':'#229971','ALB':'#1868DB','SAR':'#1868DB',
      'HUL':'#01C00E','MAG':'#01C00E','TSU':'#4781D7','HAD':'#6C98FF',
      'OCO':'#9C9FA2','GAS':'#00A1E8','BOT':'#9C9FA2','ZHO':'#9C9FA2',
      'LAW':'#6C98FF','RIC':'#6C98FF','ANT':'#00D7B6','DOO':'#00A1E8',
      'BOR':'#01C00E','BEA':'#9C9FA2','COL':'#00A1E8'
    } -%} {%- set ns = namespace(items=[]) -%} {%- for code, d in
    drivers.items() -%}
      {%- set pts = d.cumulative_points if d.cumulative_points is defined else [] -%}
      {%- set last = pts[-1] if pts else 0 -%}
      {%- set name = d.name if d.name is defined else (d.tla if d.tla is defined else code) -%}
      {%- set js = "const a = entity.attributes || {}; const rounds = a.rounds || []; const drv = (a.drivers && a.drivers['" ~ code ~ "']) || {}; const pts = drv.cumulative_points || []; return pts.map((y, i) => { const r = rounds[i] || {}; const rn = (r.round != null) ? r.round : (i+1); const label = 'R' + rn + ' — ' + (r.race_name || ''); return { x: label, y: y }; });" -%}
      {%- set obj = {
        "entity": e,
        "name": name,
        "type": "line",
        "color": palette.get(code, "#888888"),
        "data_generator": js
      } -%}
      {%- set ns.items = ns.items + [ {"code": code, "last": last, "obj": obj} ] -%}
    {%- endfor -%} [ {%- for it in ns.items | sort(attribute='last',
    reverse=true) -%}
      {{ it.obj | tojson }}{{ "," if not loop.last }}
    {%- endfor -%} ]
```


#### Constructors Progression Chart

```yaml
type: custom:auto-entities
card_param: series
show_empty: false
card:
  type: custom:apexcharts-card
  header:
    show: true
    title: Season progression - constructors points
    show_states: false
  apex_config:
    chart:
      animations:
        enabled: false
    markers:
      size: 6
      strokeWidth: 2
      hover:
        sizeOffset: 8
    states:
      hover:
        filter:
          type: darken
          value: 0.45
      active:
        allowMultipleDataPointsSelection: false
        filter:
          type: darken
          value: 0.55
    legend:
      show: true
      position: left
      horizontalAlign: left
      itemMargin:
        vertical: 4
      fontSize: 12px
    xaxis:
      type: category
      tickPlacement: between
      labels:
        rotate: -35
        trim: false
        minHeight: 60
    tooltip:
      shared: false
      intersect: true
      x:
        formatter: |
          EVAL:function (val) { return val; }
      "y":
        formatter: |
          EVAL:function (val) { return Math.round(val); }
filter:
  template: >
    {%- set e = 'sensor.f1_constructor_points_progression' -%} {%- set teams =
    state_attr(e, 'constructors') or {} -%} {# Färg per team (ändra fritt) #}
    {%- set palette = {
      'mclaren':'#F47600', 'red_bull':'#4781D7', 'mercedes':'#00D7B6',
      'williams':'#1868DB', 'aston_martin':'#229971', 'sauber':'#01C00E',
      'ferrari':'#ED1131', 'alpine':'#00A1E8', 'rb':'#6C98FF', 'haas':'#9C9FA2'
    } -%} {%- set ns = namespace(items=[]) -%} {%- for key, t in teams.items()
    -%}
      {%- set pts = t.cumulative_points if t.cumulative_points is defined else [] -%}
      {%- set last = pts[-1] if pts else 0 -%}
      {%- set name =
            (t.identity.name if t.identity is defined and t.identity.name is defined
             else (t.name if t.name is defined
             else (key | replace('_',' ') | title))) -%}
      {%- set js = "const a = entity.attributes || {}; const rounds = a.rounds || []; const team = (a.constructors && a.constructors['" ~ key ~ "']) || {}; const pts = team.cumulative_points || []; return pts.map((y, i) => { const r = rounds[i] || {}; const rn = (r.round != null) ? r.round : (i+1); const label = 'R' + rn + ' — ' + (r.race_name || ''); return { x: label, y: y }; });" -%}
      {%- set obj = {
        "entity": e,
        "name": name,
        "type": "line",
        "color": palette.get(key, "#888888"),
        "data_generator": js
      } -%}
      {%- set ns.items = ns.items + [ {"key": key, "last": last, "obj": obj} ] -%}
    {%- endfor -%} [ {%- for it in ns.items | sort(attribute='last',
    reverse=true) -%}
      {{ it.obj | tojson }}{{ "," if not loop.last }}
    {%- endfor -%} ]
```
# UKHO Tides

A [Home Assistant (HASS)](https://www.home-assistant.io/) integration to show tide information for stations provided by the [UK Hydrographic Office (UKHO)](https://www.admiralty.co.uk/ukho/About-Us).

It provides an entity for each station that you follow, showing whether the tide is currently rising or falling, and how long until the next high and low tides.

![Image of dashboard widget](docs/card.PNG)

![Image of sensor](docs/sensor.PNG)

![Image of card with attributes](docs/card_attributes.PNG)

![Image of Apex chart](docs/apex_chart.PNG)

Height chart displayed via the [ApexCharts Lovelace UI card](https://github.com/RomRider/apexcharts-card). See below for details.

# How?

This integration plugs into the [Admiralty Tidal API](https://admiraltyapi.portal.azure-api.net/) via the [ukhotides PyPI package](https://pypi.org/project/ukhotides/), which [I also wrote](https://github.com/ianByrne/PyPI-ukhotides) for this project.

# Why?

I've only recently fallen into the rabbit hole that is home automation, and this is my first attempt at a custom integration for HASS. Admittedly, I can think of very few use cases for such an integration. Maybe it would be useful for someone living on a house boat... Either way, this project has mostly been an opportunity to learn more about how HASS works, as well as is my first foray into Python.

# Installation

## API Key

First up, you will need an API key from the Admiralty Maritime Data Solutions developer portal. Follow [their guide](https://developer.admiralty.co.uk/docs/startup) on how to do so and select one of the **UK Tidal API** products - the **Discovery** tier is free (the paid APIs are untested for this integration, but should in theory work fine).

Note that the "Products" section expands over several pages, with the "UK Tidal API - Discovery" option a bit harder to find on the second page. Alternatively you can also use the search function at the top right to find the string "discovery" and it should show up in the results list.

## Installation

### Home Assistant Community Store (HACS)

I am still working on submitting this as a [HACS](https://hacs.xyz/) integration, however in the meantime you can still use the "Custom Repository" feature of HACS to download it. Alternatively, the manual download steps are in the next section.

1. From the HACS page in Home Assistant, select the three dot menu and then "Custom Repositories"
2. Paste the URL of this GitHub repo into the URL field and select "Integration" from the Category dropdown
3. Click "Add" and this will download the files into your `custom_components` directory
4. Follow the steps in the Configuration section

### Manual Download

For manual installation, simply copy/download the `ukho_tides` directory from this repo directly into your `custom_components` directory.

## Configuration

Once the files are in your `custom_components` directory, it can then be configured via either the User Interface, or the `configuration.yaml` file.

### User Interface

In HASS, navigate to **Configuration --> Integrations --> Add Integration** and then search for **UKHO Tides**.

Follow the prompts to select the API level you are using and paste your API key.

![Image of sensor auth](docs/auth.PNG)

Use the dropdown menu to select which station(s) you would like to follow.

![Image of station select](docs/station_select.PNG)

Enter a custom name for each station, as well as any offset (in minutes) from which to adjust the tide data. Unfortunately, due to a limitation in the UI configuration, this section has no labels. The order of fields, from top to bottom, is 'Station Name', 'High Tide Offset', 'Low Tide Offset'.

![Image of station settings](docs/station_settings.PNG)

### configuration.yaml

The above steps make use of the UI to configure the component. The legacy way is via the `configuration.yaml` file. Simply add the following entry, and then restart your HASS:

```yaml
sensor:
  - platform: ukho_tides
    api_key: <api_key>
    stations:
      - station_id: '0001'
      - station_id: '0113'
        station_name: 'London Bridge'
        station_offset_high: -45
        station_offset_low: 60
```

To find the id of the station(s) you would like to follow, you can use the [Easytide service](http://www.ukho.gov.uk/Easytide/easytide/SelectPort.aspx) on the UKHO website to look up a station, either on the map or via the search tab. Once a port is selected, check the URL for the `PortID` parameter and make note of its value.

For example, the station Id for St Mary's is `0001` and can be seen in its URL below:

> http://www.ukho.gov.uk/easytide/easytide/ShowPrediction.aspx?PortID=0001&PredictionLength=7

## Height Chart

You can display a height chart on the dashboard via the [ApexCharts Lovelace UI card](https://github.com/RomRider/apexcharts-card).

![Image of Apex chart](docs/apex_chart.PNG)

See their docs for how to install it - this example is using the following configuration:

```yaml
type: 'custom:apexcharts-card'
graph_span: 2d
span:
  start: hour
  offset: '-5h'
now:
  show: true
  label: now
series:
  - entity: sensor.london_bridge_tower_pier_tide
    unit: m
    data_generator: |
      return entity.attributes.predictions.map((event) => {
        return [moment.utc(event[0]).local(), event[1]];
      });
```

## Custom Card With Attributes

There are a number of attributes that can be displayed:

| Attribute | Example |
| -- | -- |
| `next_high_tide_in` | 11h 25m |
| `next_low_tide_in` | 6h 57m |
| `next_high_tide_at` | 7 January 2022, 01:02:14 |
| `next_low_tide_at` | 7 January 2022, 05:30:26 |
| `next_high_tide_height` | 5.4m |
| `next_low_tide_height` | 0.2m |
| `predictions` | Contains a list of upcoming predictions for internal use |

You can use an Entities Card to display them on your Lovelace Dashboard:

```yaml
type: entities
entities:
  - entity: sensor.hammersmith_bridge_tide
    name: Tide State
  - type: attribute
    entity: sensor.hammersmith_bridge_tide
    attribute: next_high_tide_in
    name: Next High Tide In
    icon: mdi:waves
  - type: attribute
    entity: sensor.hammersmith_bridge_tide
    attribute: next_high_tide_height
    name: Next High Tide Height
    icon: mdi:waves
  - type: attribute
    entity: sensor.hammersmith_bridge_tide
    attribute: next_low_tide_in
    name: Next Low High Tide In
    icon: mdi:wave
  - type: attribute
    entity: sensor.hammersmith_bridge_tide
    attribute: next_low_tide_height
    name: Next Low High Tide Height
    icon: mdi:wave
title: Local Tides
```

![Image of card with attributes](docs/card_attributes.PNG)

Note that a full list of icons can be found at the [Material Design Icons site](https://materialdesignicons.com/icon/home-assistant).

# TODO

- Webhooks to automate distribution and versioning
- Submit to HACS
- Submit to HASS

# Attribution

Contains ADMIRALTY® Tidal Data: © Crown copyright and database right
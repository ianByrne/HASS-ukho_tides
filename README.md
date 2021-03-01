# UKHO Tides

A [Home Assistant (HASS)](https://www.home-assistant.io/) integration to show tide information for stations provided by the [UK Hydrographic Office (UKHO)](https://www.admiralty.co.uk/ukho/About-Us).

It provides an entity for each station that you follow, showing whether the tide is currently rising or falling.

![Image of dashboard widget](https://raw.githubusercontent.com/ianByrne/HASS-ukho_tides/main/docs/card.PNG)

![Image of sensor attributes](https://raw.githubusercontent.com/ianByrne/HASS-ukho_tides/main/docs/attributes.PNG)

# How?

This integration plugs into the [Admiralty Tidal API](https://admiraltyapi.portal.azure-api.net/) via the [ukhotides PyPI package](https://pypi.org/project/ukhotides/), which [I also wrote](https://github.com/ianByrne/PyPI-ukhotides) for this project.

# Why?

I've only recently fallen into the rabbit hole that is home automation, and this is my first attempt at a custom integration for HASS. Admittedly, I can think of very few use cases for such an integration. Maybe it would be useful for someone living on a house boat... Either way, this project has mostly been an opportunity to learn more about how HASS works, as well as is my first foray into Python.

# Installation

## Prerequisites

### API Key

First up, you will need an API key from the Admiralty Maritime Data Solutions developer portal. Follow [their guide](https://admiraltyapi.portal.azure-api.net/docs/startup) on how to do so and select one of the **UK Tidal API** products - the **Discovery** tier is free (the paid APIs are untested for this integration).

### Station Ids

Next you will need to make note of which station(s) you would like to follow. You can use the [Easytide service](http://www.ukho.gov.uk/Easytide/easytide/SelectPort.aspx) on the UKHO website to find a station, either on the map or via the search tab. Once a port is selected, check the URL for the `PortID` parameter and make note of its value.

For example, the station Id for St Mary's is `0001` and can be seen in its URL below:

> http://www.ukho.gov.uk/easytide/easytide/ShowPrediction.aspx?PortID=0001&PredictionLength=7

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

Follow the prompts to paste your API key and enter the id of a station that you would like to follow. To add multiple stations, check the "Add another" box before continuing. You can also set a custom name for the station - if left blank, it will use UKHO's name.

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
```

# TODO

- Implement "options" flow to add/remove stations via the UI
- Generate pretty charts for the dashboard
- Webhooks to automate distribution and versioning
- Submit to HACS
- Submit to HASS
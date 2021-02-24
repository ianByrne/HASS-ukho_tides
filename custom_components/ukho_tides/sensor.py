import datetime
import logging

from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, COORDINATOR, ATTRIBUTION, ATTR_ICON_RISING, ATTR_ICON_FALLING

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]

    sensors = []
    sensors.append(UkhoTidePredictionsSensor(coordinator))

    async_add_entities(sensors, False)


class UkhoTidePredictionsSensor(CoordinatorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._name = coordinator.station_name + " Tide"
        self._attrs = {ATTR_ATTRIBUTION: ATTRIBUTION}

    @property
    def name(self):
        if self._name:
            return self._name

        return "Unknown"

    @property
    def unique_id(self):
        return self.coordinator.station_id

    @property
    def state(self):
        if self.coordinator.data is None:
            return None

        nextPrediction = self.get_next_prediction()

        if nextPrediction["EventType"] == "HighWater":
            return "Rising"
        else:
            return "Falling"

    @property
    def icon(self):
        if self.coordinator.data is None:
            return None

        nextPrediction = self.get_next_prediction()

        if nextPrediction["EventType"] == "HighWater":
            return ATTR_ICON_RISING
        else:
            return ATTR_ICON_FALLING

    @property
    def device_state_attributes(self):
        nextPrediction = self.get_next_prediction()

        now = datetime.datetime.utcnow()

        timeToNextTide = nextPrediction["DateTimeObject"] - now
        nextHeight = round(nextPrediction["Height"], 1)

        hours, rem = divmod(timeToNextTide.seconds, 3600)
        minutes, seconds = divmod(rem, 60)

        if nextPrediction["EventType"] == "HighWater":
            kind = "high"
        else:
            kind = "low"

        self._attrs[f"{kind}_tide_in"] = f"{hours}h {minutes}m"
        self._attrs[f"{kind}_tide_height"] = f"{nextHeight}m"

        return self._attrs

    def get_next_prediction(self):
        now = datetime.datetime.utcnow()

        for prediction in self.coordinator.data:
            prediction["DateTimeObject"] = datetime.datetime.strptime(
                prediction["DateTime"].split(".")[0], "%Y-%m-%dT%H:%M:%S"
            )

            if prediction["DateTimeObject"] > now:
                return prediction

        return None
"""Platform for OpenRGB Integration."""
import logging

from openrgb import utils as RGBUtils

# Import the device class from the component that you want to support
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    DOMAIN as SENSOR_DOMAIN,
    ColorMode,
    LightEntityFeature,
    LightEntity,
)
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers import entity_registry as er
import homeassistant.util.color as color_util

from .const import (
    CONF_ADD_LEDS,
    DOMAIN,
    EFFECT_DIRECT,
    EFFECT_OFF,
    EFFECT_STATIC,
    ORGB_DISCOVERY_NEW,
    SIGNAL_DELETE_ENTITY,
    SIGNAL_UPDATE_ENTITY,
)
from .helpers import orgb_entity_id, orgb_icon, orgb_object_id, orgb_tuple

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up OpenRGB devices dynamically."""

    async def async_discover_sensor(entry_id, dev_ids):
        """Discover and add a discovered openrgb sensor."""
        if not dev_ids or entry_id != config_entry.entry_id:
            return

        entities = await hass.async_add_executor_job(
            _setup_entities,
            hass,
            config_entry.entry_id,
            dev_ids,
            config_entry.data[CONF_ADD_LEDS] if CONF_ADD_LEDS in config_entry.data else False,
        )
        async_add_entities(entities, True)

    async_dispatcher_connect(
        hass, ORGB_DISCOVERY_NEW.format(SENSOR_DOMAIN), async_discover_sensor
    )

    device_ids = hass.data[DOMAIN][config_entry.entry_id]["pending"].pop(SENSOR_DOMAIN)
    await async_discover_sensor(config_entry.entry_id, device_ids)


def _setup_entities(hass, entry_id, dev_ids, add_leds):
    """Set up OpenRGB Light device."""
    entities = []
    for dev_id in dev_ids:
        if dev_id is None:
            continue

        entity_id = orgb_entity_id(dev_id)
        ha_dev_unique_id = hass.data[DOMAIN][entry_id]["ha_dev_unique_id"]
        device_unique_id = dev_id.metadata.serial
        # Some devices don't have a serial defined, so fall back to OpenRGB id
        if not device_unique_id:
            device_unique_id = entity_id

        if not hass.data[DOMAIN][entry_id]["entities"].get(device_unique_id, None):
            entities.append(OpenRGBDevice(hass, ha_dev_unique_id, entry_id, dev_id, device_unique_id))

        if add_leds:
            for led in dev_id.leds:
                led_unique_id = f"{device_unique_id}_led_{led.id}"
                if not hass.data[DOMAIN][entry_id]["entities"].get(led_unique_id, None):
                    entities.append(OpenRGBLed(hass, ha_dev_unique_id, entry_id, dev_id, led.id, led_unique_id))
    return entities

class OpenRGBLight(LightEntity):
    """Representation of a OpenRGB Device."""

    def __init__(self, hass, ha_dev_id, entry_id):
        """Initialize an OpenRGB light."""
        self._hass = hass
        self._ha_dev_id = ha_dev_id
        self._entry_id = entry_id

    async def async_added_to_hass(self):
        """Call when entity is added to hass."""
        return NotImplemented

    async def async_will_remove_from_hass(self):
        """Cleanup signal handlers."""
        for signal_callback in self._callbacks:
            signal_callback()

    # Device Properties

    @property
    def object_id(self):
        """Return the OpenRGB id."""
        return orgb_object_id(self._light)
    
    @property
    def device_info(self):
        return {
            "identifiers": {
                (
                    DOMAIN, 
                    f'{self._ha_dev_id}_{orgb_entity_id(self._light)}'
                )
            },
            "name": self._light.name,
            "manufacturer": self._light.metadata.vendor,
            "model": self._light.metadata.description,
            "sw_version": self._light.metadata.version,
        }

    @property
    def icon(self):
        """Give this device an icon representing what it is."""
        return "mdi:{}".format(orgb_icon(self._light.type))

    @property
    def name(self):
        """Return the display name of the light."""
        return self._name

    @property
    def available(self):
        """Return if the device is online."""
        return self.hass.data[DOMAIN][self._entry_id]["online"]

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._state

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        return self._brightness
    
    @property
    def color_mode(self):
        """Return the color mode of the light."""
        return ColorMode.HS
    
    @property
    def supported_color_modes(self):
        """Return a set of supported color modes."""
        return {ColorMode.HS}

    @property
    def hs_color(self):
        """Return the hue and saturation color value [float, float]."""
        return self._hs_value

    @property
    def assumed_state(self):
        """Return if the state is assumed."""
        return self._assumed_state

    # Public interfaces to control the device

    def turn_on(self, **kwargs):
        """Turn the device on, and set defaults."""
        if ATTR_HS_COLOR in kwargs:
            self._hs_value = kwargs.get(ATTR_HS_COLOR)

        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs.get(ATTR_BRIGHTNESS)

        # Restore the state if the light just gets turned on
        if not kwargs:
            self._brightness = 255.0 if self._prev_brightness == 0.0 else self._prev_brightness
            self._hs_value = self._prev_hs_value

        self._device_turned_on(**kwargs)

        self._set_color()
        self._state = True

    def turn_off(self, **kwargs):
        """Turn the device off."""
        # prevent subsequent turn_off calls from erasing the previous state
        if not self.is_on:
            return

        self._device_turned_off(**kwargs)

        self._state = False

    def _device_turned_on(self, **kwargs):
        pass

    def _device_turned_off(self, **kwargs):
        pass

    def _retrieve_current_name(self) -> str:
        raise NotImplementedError

    def _retrieve_current_hsv_color(self) -> tuple[float, float, float]:
        raise NotImplementedError

    def update(self):
        """Single function to update the devices state."""
        self._name = self._retrieve_current_name()
        hsv_color = self._retrieve_current_hsv_color()
        self._hs_value = (hsv_color[0], hsv_color[1])
        self._brightness = 255.0 * (hsv_color[2] / 100.0)

        # Infer the state from the brightness
        self._state = self._brightness > 0.0

        # After updating, we no longer need to assume the state
        self._assumed_state = False

    def _set_color(self):
        """Set the devices color using the library."""
        raise NotImplementedError

    # Callbacks
    @callback
    async def _delete_callback(self, dev_id):
        """Remove this entity."""
        if dev_id == self.entity_id:
            entity_registry = (
                er.async_get(self.hass)
            )
            if entity_registry.async_is_registered(self._attr_unique_id):
                entity_registry.async_remove(self._attr_unique_id)
            else:
                await self.async_remove()

    @callback
    async def _update_callback(self, dev_id=None):
        self.async_schedule_update_ha_state(True)

class OpenRGBDevice(OpenRGBLight):
    """Representation of an OpenRGB Device."""

    def __init__(self, hass, ha_dev_unique_id, entry_id, light, unique_id):
        """Initialize an OpenRGB light."""
        super().__init__(hass, ha_dev_unique_id, entry_id)
        self._light = light
        self._callbacks = []
        self._unique_id = unique_id
        self._attr_unique_id = f'{ha_dev_unique_id}_{unique_id}'
        self._name = self._retrieve_current_name()

        self._brightness = 255.0
        self._prev_brightness = 255.0

        self._hs_value = (0.0, 0.0)
        self._prev_hs_value = (0.0, 0.0)

        self._effect = ""
        self._prev_effect = self._light.modes[self._light.active_mode].name

        self._effects = []

        self._state = True
        self._assumed_state = True
        
    async def async_added_to_hass(self):
        """Call when entity is added to hass."""
        self.hass.data[DOMAIN][self._entry_id]["entities"][self._unique_id] = self._attr_unique_id
        self._callbacks.append(
            async_dispatcher_connect(
                self.hass, SIGNAL_DELETE_ENTITY, self._delete_callback
            )
        )
        self._callbacks.append(
            async_dispatcher_connect(
                self.hass, SIGNAL_UPDATE_ENTITY, self._update_callback
            )
        )

    @property
    def effect_list(self):
        """Return the list of supported effects."""
        return self._effects

    @property
    def effect(self):
        """Return the current effect."""
        return self._effect

    @property
    def supported_features(self):
        """Return the supported features for this device."""
        return LightEntityFeature.EFFECT

    def _device_turned_on(self, **kwargs):
        if ATTR_EFFECT in kwargs:
            self._effect = kwargs.get(ATTR_EFFECT)

        if not kwargs:
            if self._prev_effect != EFFECT_OFF:
                # restore the state
                self._effect = self._prev_effect

            if self._effect == EFFECT_OFF:
                # If the light got initialized with the Off effect, switching
                # the effect to Static or Direct is the best we can do.
                if EFFECT_STATIC in [mode.name for mode in self._light.modes]:
                    self._effect = EFFECT_STATIC
                elif EFFECT_DIRECT in [mode.name for mode in self._light.modes]:
                    self._effect = EFFECT_DIRECT
                else:
                    _LOGGER.warning(
                        "The light %s could not be turned on because it does not support 'Static' or 'Direct' effects.",
                        self._name,
                    )
                    return

        self._set_effect()

    def _device_turned_off(self, **kwargs):
        if self._effect != EFFECT_OFF:
            # preserve the state
            self._prev_brightness = self._brightness
            self._prev_hs_value = self._hs_value
            self._prev_effect = self._effect

            # Use the Off effect if available
            if EFFECT_OFF in [mode.name for mode in self._light.modes]:
                self._effect = EFFECT_OFF
                self._set_effect()
            else:
                # Otherwise, turn brightness to 0
                self._brightness = 0.0
                self._set_color()

    def _retrieve_current_name(self) -> str:
        return f"{self._light.name} {self._light.device_id}"

    def _retrieve_current_hsv_color(self) -> tuple[float, float, float]:
        return color_util.color_RGB_to_hsv(*orgb_tuple(self._light.colors[0]))

    def update(self):
        super().update()

        self._effect = self._light.modes[self._light.active_mode].name
        self._effects = [mode.name for mode in self._light.modes if mode.name != EFFECT_OFF]

        # If the effect is Off, the light is off
        if self._effect == EFFECT_OFF:
            self._state = False

    # Functions to modify the devices state
    def _set_effect(self):
        """Set the devices effect."""
        try:
            self._light.set_mode(self._effect)
        except ConnectionError:
            self.hass.data[DOMAIN][self._entry_id]["connection_failed"]()

    def _set_color(self):
        """Set the devices color using the library."""
        color = color_util.color_hsv_to_RGB(
            *(self._hs_value), 100.0 * (self._brightness / 255.0)
        )
        try:
            self._light.set_color(RGBUtils.RGBColor(*color))
            self._assumed_state = False
        except ConnectionError:
            self.hass.data[DOMAIN][self._entry_id]["connection_failed"]()

class OpenRGBLed(OpenRGBLight):
    """Representation of a LED from an OpenRGB Device."""

    def __init__(self, hass, ha_dev_unique_id, entry_id, light, led_id, unique_id):
        """Initialize an OpenRGB light."""
        super().__init__(hass, ha_dev_unique_id, entry_id)
        self._light = light
        self._callbacks = []
        self._led_id = led_id
        self._unique_id = unique_id
        self._attr_unique_id = f'{ha_dev_unique_id}_{unique_id}'
        self._name = self._retrieve_current_name()
        _LOGGER.debug ("led name: %s", self._name)

        self._brightness = 255.0
        self._prev_brightness = 255.0

        self._hs_value = (0.0, 0.0)
        self._prev_hs_value = (0.0, 0.0)

        self._state = True
        self._assumed_state = True

    async def async_added_to_hass(self):
        """Call when entity is added to hass."""

        self.hass.data[DOMAIN][self._entry_id]["entities"][self._unique_id] = self._attr_unique_id
        self._callbacks.append(
            async_dispatcher_connect(
                self.hass, SIGNAL_DELETE_ENTITY, self._delete_callback
            )
        )
        self._callbacks.append(
            async_dispatcher_connect(
                self.hass, SIGNAL_UPDATE_ENTITY, self._update_callback
            )
        )

    @property
    def led_id(self):
        """Return the id of the assigned led."""
        return self._led_id

    @property
    def supported_features(self):
        """Return the supported features for this device."""
        return LightEntityFeature(0)

    def _device_turned_off(self, **kwargs):
        if self._brightness != 0.0:
            # preserve the state
            self._prev_brightness = self._brightness
            self._prev_hs_value = self._hs_value

            self._brightness = 0.0
            self._set_color()

    def _retrieve_current_name(self) -> str:
        return f"{self._light.name} {self._light.device_id} LED {self._led_id}"
        return f"{self._light.name} {self._light.device_id} {self._light.leds[self._led_id].name}"

    def _retrieve_current_hsv_color(self) -> tuple[float, float, float]:
        return color_util.color_RGB_to_hsv(*orgb_tuple(self._light.colors[self._led_id]))

    def _set_color(self):
        """Set the devices color using the library."""
        color = color_util.color_hsv_to_RGB(
            *(self._hs_value), 100.0 * (self._brightness / 255.0)
        )
        try:
            self._light.leds[self._led_id].set_color(RGBUtils.RGBColor(*color))
            self._assumed_state = False
        except ConnectionError:
            self.hass.data[DOMAIN][self._entry_id]["connection_failed"]()
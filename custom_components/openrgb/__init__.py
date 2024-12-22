"""The OpenRGB integration."""
import asyncio
import logging

from openrgb import OpenRGBClient
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import CONF_CLIENT_ID, CONF_HOST, CONF_PORT
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_ADD_LEDS,
    CONFIG_VERSION,
    DEFAULT_ADD_LEDS,
    DEFAULT_CLIENT_ID,
    DEFAULT_PORT,
    DOMAIN,
    ENTRY_IS_SETUP,
    ORGB_DATA,
    ORGB_DISCOVERY_NEW,
    ORGB_TRACKER,
    SERVICE_FORCE_UPDATE,
    SERVICE_PULL_DEVICES,
    SIGNAL_DELETE_ENTITY,
    SIGNAL_UPDATE_ENTITY,
    TRACK_INTERVAL,
)
from .helpers import orgb_entity_id

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    vol.All(
        cv.deprecated(DOMAIN),
        {
            DOMAIN: vol.Schema(
                {
                    vol.Required(CONF_HOST): cv.string,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                    vol.Optional(CONF_CLIENT_ID, default=DEFAULT_CLIENT_ID): cv.string,
                    vol.Optional(CONF_ADD_LEDS, default=DEFAULT_ADD_LEDS): cv.boolean,
                }
            )
        },
    ),
    extra=vol.ALLOW_EXTRA,
)

def autolog(message):
    "Automatically log the current function details."
    import inspect
    # Get the previous frame in the stack, otherwise it would
    # be this function!!!
    func = inspect.currentframe().f_back.f_code
    # Dump the message + the name of this function to the log.
    _LOGGER.debug("%s: %s in %s:%i" % (
        message, 
        func.co_name, 
        func.co_filename, 
        func.co_firstlineno
    ))

async def async_migrate_entry(hass, config_entry: ConfigEntry):
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    update = False
    new = {**config_entry.data}

    if config_entry.version == 1:
        config_entry.unique_id = f'{DOMAIN}_{config_entry.data[CONF_HOST]}_{config_entry.data[CONF_PORT]}'
        update = True

    if update:
        _LOGGER.info("Migration from version %s to %s successful", config_entry.version, CONFIG_VERSION)
        config_entry.version = CONFIG_VERSION
        hass.config_entries.async_update_entry(config_entry, data=new)

    return True

async def async_setup(hass, config):
    """Set up the OpenRGB integration."""
    conf = config.get(DOMAIN)
    if conf is not None:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=conf
            )
        )

    return True


async def async_setup_entry(hass, entry):
    """Set up OpenRGB platform."""

    config = {}
    for key, value in entry.data.items():
        config[key] = value
    for key, value in entry.options.items():
        config[key] = value
    if entry.options:
        hass.config_entries.async_update_entry(entry, data=config, options={})

    _LOGGER.debug("Initializing OpenRGB entry (%s)", config)

    undo_listener = entry.add_update_listener(_update_listener)

    try:
        orgb = OpenRGBClient(
            config[CONF_HOST],
            config[CONF_PORT],
            name=config[CONF_CLIENT_ID],
        )
    except ConnectionError as err:
        _LOGGER.error("Connection error during integration setup. Error: %s", err)
        raise ConfigEntryNotReady
    except:
        _LOGGER.debug("Connection error during integration setup.")
        raise ConfigEntryNotReady
    autolog(">>>")

    _LOGGER.info("Initialized OpenRGB entry (%s)", config)

    def connection_recovered():
        autolog("<<<")
        if not hass.data[DOMAIN][entry.entry_id]["online"]:
            _LOGGER.info(
                "Connection reestablished to OpenRGB SDK Server at %s:%i",
                config[CONF_HOST],
                config[CONF_PORT],
            )

        hass.data[DOMAIN][entry.entry_id]["online"] = True
        hass.loop.call_soon_threadsafe(async_dispatcher_send, hass, SIGNAL_UPDATE_ENTITY)
        autolog(">>>")

    def connection_failed():
        autolog("<<<")
        if hass.data[DOMAIN][entry.entry_id]["online"]:
            hass.data[DOMAIN][entry.entry_id][ORGB_DATA].disconnect()
            _LOGGER.warn(
                "Connection lost to OpenRGB SDK Server at %s:%i",
                config[CONF_HOST],
                config[CONF_PORT],
            )

        hass.data[DOMAIN][entry.entry_id]["online"] = False
        hass.loop.call_soon_threadsafe(async_dispatcher_send, hass, SIGNAL_UPDATE_ENTITY)
        autolog(">>>")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "ha_dev_unique_id": f'{DOMAIN}_{entry.data[CONF_HOST]}_{entry.data[CONF_PORT]}',
        "online": True,
        ORGB_DATA: orgb,
        ORGB_TRACKER: None,
        ENTRY_IS_SETUP: set(),
        "entities": {},
        "pending": {},
        "devices": {},
        "unlistener": undo_listener,
        "connection_failed": connection_failed,
        "connection_recovered": connection_recovered,
    }

    # Initial device load
    async def async_load_devices(device_list):
        autolog("<<<")

        device_type_list = {}

        for device in device_list:
            ha_type = "light"
            if ha_type not in device_type_list:
                device_type_list[ha_type] = []
            device_type_list[ha_type].append(device)

            entity_id = orgb_entity_id(device)
            device_unique_id = device.metadata.serial
            # Some devices don't have a serial defined, so fall back to OpenRGB id
            if not device_unique_id:
                device_unique_id = entity_id

            if entity_id not in hass.data[DOMAIN][entry.entry_id]["devices"]:
                hass.data[DOMAIN][entry.entry_id]["devices"][entity_id] = []
            
            # Stores the entire device as an entity
            if device_unique_id not in hass.data[DOMAIN][entry.entry_id]["entities"]:
                hass.data[DOMAIN][entry.entry_id]["entities"][device_unique_id] = None
            
            if CONF_ADD_LEDS in config and config[CONF_ADD_LEDS]:
                # Stores each LED of the device as an entity
                for led in device.leds:
                    led_unique_id = f"{device_unique_id}_led_{led.id}"
                    if led_unique_id not in hass.data[DOMAIN][entry.entry_id]["entities"]:
                        hass.data[DOMAIN][entry.entry_id]["entities"][led_unique_id] = None

        for ha_type, dev_ids in device_type_list.items():
            config_entries_key = f"{ha_type}.openrgb"

            if config_entries_key not in hass.data[DOMAIN][entry.entry_id][ENTRY_IS_SETUP]:
                hass.data[DOMAIN][entry.entry_id]["pending"][ha_type] = dev_ids
                hass.async_create_task(
                    hass.config_entries.async_forward_entry_setup(entry, "light")
                )
                hass.data[DOMAIN][entry.entry_id][ENTRY_IS_SETUP].add(config_entries_key)
            else:
                hass.loop.call_soon_threadsafe(
                    async_dispatcher_send,
                    hass,
                    ORGB_DISCOVERY_NEW.format("light"),
                    entry.entry_id,
                    device_list,
                )


        autolog(">>>")

    def _get_updated_devices():
        autolog("<<<")
        if hass.data[DOMAIN][entry.entry_id]["online"]:
            try:
                orgb.update()
                return orgb.devices
            except OSError:
                autolog(">>>exception")
                hass.data[DOMAIN][entry.entry_id]["connection_failed"]()
                return None
        else:
            hass.data[DOMAIN][entry.entry_id]["connection_failed"]()
            autolog(">>>")
            return None

    device_list = await hass.async_add_executor_job(_get_updated_devices)
    _LOGGER.debug("hass device list: %s", device_list)
    if device_list is not None:
        await async_load_devices(device_list)

    async def async_poll_devices_update(event_time):
        autolog("<<<")
        _LOGGER.debug("hass data: %s", hass.data[DOMAIN])

        if not hass.data[DOMAIN][entry.entry_id]["online"]:
            # try to reconnect
            try:
                hass.data[DOMAIN][entry.entry_id][ORGB_DATA].connect()
                hass.data[DOMAIN][entry.entry_id]["connection_recovered"]()
            except OSError:
                hass.data[DOMAIN][entry.entry_id]["connection_failed"]()
                return

        device_list = await hass.async_add_executor_job(_get_updated_devices)
        if device_list is None:
            return

        await async_load_devices(device_list)

        _LOGGER.debug("hass data newlist: %s", device_list)

        newlist_ids = []
        for device in device_list:
            newlist_ids.append(orgb_entity_id(device))
        for dev_id in list(hass.data[DOMAIN][entry.entry_id]["devices"]):
            # Clean up stale devices, or alert them that new info is available.
            if dev_id not in newlist_ids:
                hass.loop.call_soon_threadsafe(async_dispatcher_send, hass, SIGNAL_DELETE_ENTITY, dev_id)
                
                for led_id in hass.data[DOMAIN][entry.entry_id]["devices"][dev_id]:
                    hass.loop.call_soon_threadsafe(async_dispatcher_send, hass, SIGNAL_DELETE_ENTITY, led_id)

                hass.data[DOMAIN][entry.entry_id]["devices"].pop(dev_id)
            else:
                hass.loop.call_soon_threadsafe(async_dispatcher_send, hass, SIGNAL_UPDATE_ENTITY, dev_id)
                
                for led_id in hass.data[DOMAIN][entry.entry_id]["devices"][dev_id]:
                    hass.loop.call_soon_threadsafe(async_dispatcher_send, hass, SIGNAL_UPDATE_ENTITY, led_id)

        autolog(">>>")


    hass.data[DOMAIN][entry.entry_id][ORGB_TRACKER] = async_track_time_interval(
        hass, async_poll_devices_update, TRACK_INTERVAL
    )

    hass.services.async_register(
        DOMAIN, SERVICE_PULL_DEVICES, async_poll_devices_update
    )

    async def async_force_update(call):
        """Force all devices to pull data."""
        hass.loop.call_soon_threadsafe(async_dispatcher_send, hass, SIGNAL_UPDATE_ENTITY)

    hass.services.async_register(DOMAIN, SERVICE_FORCE_UPDATE, async_force_update)

    return True

async def _update_listener(hass, config_entry):
    """Update listener."""
    await hass.config_entries.async_reload(config_entry.entry_id)

async def async_unload_entry(hass, entry):
    """Unloading the OpenRGB platforms."""
    autolog("<<<")

    _LOGGER.info("Unloading OpenRGB")

    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(
                    entry, component.split(".", 1)[0]
                )
                for component in hass.data[DOMAIN][entry.entry_id][ENTRY_IS_SETUP]
            ]
        )
    )

    if unload_ok:
        hass.data[DOMAIN][entry.entry_id][ENTRY_IS_SETUP] = set()
        hass.data[DOMAIN][entry.entry_id][ORGB_TRACKER]()
        hass.data[DOMAIN][entry.entry_id][ORGB_TRACKER] = None
        hass.data[DOMAIN][entry.entry_id][ORGB_DATA].disconnect()
        hass.data[DOMAIN][entry.entry_id][ORGB_DATA] = None
        hass.data[DOMAIN][entry.entry_id]["unlistener"]()
        hass.services.async_remove(DOMAIN, SERVICE_FORCE_UPDATE)
        hass.services.async_remove(DOMAIN, SERVICE_PULL_DEVICES)
        hass.data[DOMAIN].pop(entry.entry_id)

    autolog(">>>")

    return unload_ok

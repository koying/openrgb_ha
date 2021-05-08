"""The OpenRGB integration."""
import asyncio
import logging

from openrgb import OpenRGBClient
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_CLIENT_ID, CONF_HOST, CONF_PORT
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
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
        if not hass.data[DOMAIN]["online"]:
            _LOGGER.info(
                "Connection reestablished to OpenRGB SDK Server at %s:%i",
                config[CONF_HOST],
                config[CONF_PORT],
            )

        hass.data[DOMAIN]["online"] = True
        async_dispatcher_send(hass, SIGNAL_UPDATE_ENTITY)
        autolog(">>>")

    def connection_failed():
        autolog("<<<")
        if hass.data[DOMAIN]["online"]:
            hass.data[DOMAIN][ORGB_DATA].disconnect()
            _LOGGER.info(
                "Connection lost to OpenRGB SDK Server at %s:%i",
                config[CONF_HOST],
                config[CONF_PORT],
            )

        hass.data[DOMAIN]["online"] = False
        async_dispatcher_send(hass, SIGNAL_UPDATE_ENTITY)
        autolog(">>>")

    hass.data[DOMAIN] = {
        "online": True,
        ORGB_DATA: orgb,
        ORGB_TRACKER: None,
        ENTRY_IS_SETUP: set(),
        "entities": {},
        "pending": {},
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
            if entity_id not in hass.data[DOMAIN]["entities"]:
                hass.data[DOMAIN]["entities"][entity_id] = None

        for ha_type, dev_ids in device_type_list.items():
            config_entries_key = f"{ha_type}.openrgb"

            if config_entries_key not in hass.data[DOMAIN][ENTRY_IS_SETUP]:
                hass.data[DOMAIN]["pending"][ha_type] = dev_ids
                hass.async_create_task(
                    hass.config_entries.async_forward_entry_setup(entry, "light")
                )
                hass.data[DOMAIN][ENTRY_IS_SETUP].add(config_entries_key)
            else:
                async_dispatcher_send(
                    hass, ORGB_DISCOVERY_NEW.format("light"), device_list
                )

    def _get_updated_devices():
        autolog("<<<")
        if hass.data[DOMAIN]["online"]:
            try:
                orgb.update()
                return orgb.devices
            except OSError:
                autolog(">>>exception")
                hass.data[DOMAIN]["connection_failed"]()
                return None
        else:
            hass.data[DOMAIN]["connection_failed"]()
            return None
        autolog(">>>")

    await async_load_devices(_get_updated_devices())

    async def async_poll_devices_update(event_time):
        if not hass.data[DOMAIN]["online"]:
            # try to reconnect
            try:
                hass.data[DOMAIN][ORGB_DATA].connect()
                hass.data[DOMAIN]["connection_recovered"]()
            except OSError:
                hass.data[DOMAIN]["connection_failed"]()
                return

        device_list = await hass.async_add_executor_job(_get_updated_devices)

        if device_list is None:
            return

        await async_load_devices(device_list)

        newlist_ids = []
        for device in device_list:
            newlist_ids.append(orgb_entity_id(device))
        for dev_id in list(hass.data[DOMAIN]["entities"]):
            # Clean up stale devices, or alert them that new info is available.
            if dev_id not in newlist_ids:
                async_dispatcher_send(hass, SIGNAL_DELETE_ENTITY, dev_id)
                hass.data[DOMAIN]["entities"].pop(dev_id)
            else:
                async_dispatcher_send(hass, SIGNAL_UPDATE_ENTITY, dev_id)

    hass.data[DOMAIN][ORGB_TRACKER] = async_track_time_interval(
        hass, async_poll_devices_update, TRACK_INTERVAL
    )

    hass.services.async_register(
        DOMAIN, SERVICE_PULL_DEVICES, async_poll_devices_update
    )

    async def async_force_update(call):
        """Force all devices to pull data."""
        async_dispatcher_send(hass, SIGNAL_UPDATE_ENTITY)

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
                for component in hass.data[DOMAIN][ENTRY_IS_SETUP]
            ]
        )
    )

    if unload_ok:
        hass.data[DOMAIN][ENTRY_IS_SETUP] = set()
        hass.data[DOMAIN][ORGB_TRACKER]()
        hass.data[DOMAIN][ORGB_TRACKER] = None
        hass.data[DOMAIN][ORGB_DATA].disconnect()
        hass.data[DOMAIN][ORGB_DATA] = None
        hass.data[DOMAIN]["unlistener"]()
        hass.services.async_remove(DOMAIN, SERVICE_FORCE_UPDATE)
        hass.services.async_remove(DOMAIN, SERVICE_PULL_DEVICES)
        hass.data.pop(DOMAIN)

    autolog(">>>")

    return unload_ok

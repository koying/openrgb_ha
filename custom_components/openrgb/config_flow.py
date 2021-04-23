"""Config flow for OpenRGB."""
import asyncio
import logging
import socket

from openrgb import OpenRGBClient
import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.const import CONF_CLIENT_ID, CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .const import CONN_TIMEOUT, DEFAULT_CLIENT_ID, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

RESULT_CONN_ERROR = "cannot_connect"
RESULT_LOG_MESSAGE = {RESULT_CONN_ERROR: "Connection error"}


def _try_connect(_host, _port, _client_id):
    """Check if we can connect."""
    try:
        conn = OpenRGBClient(_host, _port, name=_client_id)
        conn.comms.stop_connection()
    except OSError as exc:
        raise CannotConnect from exc

    return True

@config_entries.HANDLERS.register(DOMAIN)
class OpenRGBFlowHandler(config_entries.ConfigFlow):
    """Config flow for OpenRGB component."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """OpenRGB options callback."""
        return OpenRGBOptionsFlowHandler(config_entry)

    def __init__(self):
        """Init OpenRGBFlowHandler."""
        self._errors = {}
        self._host = None
        self._port = DEFAULT_PORT
        self._client_id = DEFAULT_CLIENT_ID
        self._is_import = False

    async def async_step_import(self, user_input=None):
        """Handle configuration by yaml file."""
        self._is_import = True
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        self._errors = {}

        data_schema = {
            vol.Required(CONF_HOST, default=self._host): str,
            vol.Required(CONF_PORT, default=self._port): int,
            vol.Required(CONF_CLIENT_ID, default=self._client_id): str,
        }

        if user_input is not None:
            self._host = str(user_input[CONF_HOST])
            self._port = user_input[CONF_PORT]
            self._client_id = user_input[CONF_CLIENT_ID]

            try:
                await asyncio.wait_for(
                    self.hass.async_add_executor_job(_try_connect, self._host, self._port, self._client_id),
                    timeout=CONN_TIMEOUT,
                )

                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=DOMAIN,
                    data={
                        CONF_HOST: self._host,
                        CONF_PORT: self._port,
                        CONF_CLIENT_ID: self._client_id,
                    },
                )

            except (asyncio.TimeoutError, CannotConnect):
                result = RESULT_CONN_ERROR

            if self._is_import:
                _LOGGER.error(
                    "Error importing from configuration.yaml: %s",
                    RESULT_LOG_MESSAGE.get(result, "Generic Error"),
                )
                return self.async_abort(reason=result)

            self._errors["base"] = result

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=self._errors,
        )


class OpenRGBOptionsFlowHandler(config_entries.OptionsFlow):
    """Option flow for OpenRGB component."""

    def __init__(self, config_entry):
        """Init OpenRGBOptionsFlowHandler."""
        self._errors = {}
        self._host = config_entry.data[CONF_HOST] if CONF_HOST in config_entry.data else None
        self._port = config_entry.data[CONF_PORT] if CONF_PORT in config_entry.data else DEFAULT_PORT
        self._client_id = config_entry.data[CONF_CLIENT_ID] if CONF_CLIENT_ID in config_entry.data else DEFAULT_CLIENT_ID

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        self._errors = {}

        if user_input is not None:
            self._host = str(user_input[CONF_HOST])
            self._port = user_input[CONF_PORT]
            self._client_id = user_input[CONF_CLIENT_ID]

        data_schema = {
            vol.Required(CONF_HOST, default=self._host): str,
            vol.Required(CONF_PORT, default=self._port): int,
            vol.Required(CONF_CLIENT_ID, default=self._client_id): str,
        }

        if user_input is not None:
            try:
                await asyncio.wait_for(
                    self.hass.async_add_executor_job(_try_connect, self._host, self._port, self._client_id),
                    timeout=CONN_TIMEOUT,
                )

                return self.async_create_entry(
                    title=DOMAIN,
                    data={
                        CONF_HOST: self._host,
                        CONF_PORT: self._port,
                        CONF_CLIENT_ID: self._client_id,
                    },
                )

            except (asyncio.TimeoutError, CannotConnect):
                _LOGGER.error("cannot connect")
                result = RESULT_CONN_ERROR

            self._errors["base"] = result

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=self._errors,
        )

class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we can not connect."""

# OpenRGB integration for Home Assistant

## Pre-requisites

1. OpenRGB installed.
1. Its _SDK Server_ component enabled.
1. No firewall blocking the connection between Home Assistant and OpenRGB.
   1. For example, make sure your Ethernet or Wi-Fi network connection is set as _Private_ in Windows.

## Installation

The easiest install is via [HACS](https://hacs.xyz):

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=openrgb-ha&repository=openrgb-ha&category=integration)

1. Click the button above, and install this integration via HACS.
1. Restart Home Assistant.

Then click the button below to configure the integration in your Home Assistant instance:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=openrgb)

## Configuration

### Options

This integration can only be configuration through the UI (_Configuration_ -> _Devices & services_), and the options below can be configured when the integration is added.

| key       | default        | required | description                                     |
| --------- | -------------- | -------- | ----------------------------------------------- |
| host      | localhost      | yes      | The host or IP where OpenRGB is running         |
| port      | 6742           | yes      | The port on which the Server SDK is listening   |
| client_id | Home Assistant | no       | The Client ID that will be displayed in OpenRGB |

## Credits

- This custom component is a follow-up to https://github.com/home-assistant/core/pull/38309 by @bahorn, which didn't make it to HA Core.
- This integration uses [openrgb-python](https://github.com/jath03/openrgb-python), by @jath03.

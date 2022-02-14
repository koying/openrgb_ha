# OpenRGB integration for Home Assistant

## Changelog

### 2.2 [Breaking]

- Fix multiple instances

### 2.1

- Allow multiple instances (fixes #11)

### 2.0

- Add support for individual LED control (thanks @FeikoJoosten)

### 1.0

- Initial release

## Pre-requistes

1. OpenRGB installed
1. Its "SDK Server" component enabled

## Installation

### HACS

1. Launch HACS
1. Navigate to the Integrations section
1. "+ Explore & Add Repositories" button in the bottom-right
1. Search for "OpenRGB"
1. Select "Install this repository"
1. Restart Home Assistant

### Home Assistant

1. Go to the integrations page
1. Click on the "Add Integration" button at the bottom-right
1. Search for the "OpenRGB" integration
1. Select the OpenRGB integration

## Configuration

### Options

This integration can only be configuration through the UI (Configuration->Integrations), and the options below can be configured when the integration is added.

| key       | default        | required | description                                     |
| --------- | -------------- | -------- | ----------------------------------------------- |
| host      | localhost      | yes      | The host where OpenRGB is running               |
| port      | 6742           | yes      | The port on which the Server SDK is listening   |
| client_id | Home Assistant | no       | the Client ID that will be displayed in OpenRGB |

## Credits

- This custom component is a follow-up to https://github.com/home-assistant/core/pull/38309 by @bahorn, which didn't make it to HA Core.  
- This integration uses openrgb-python, by @jath03

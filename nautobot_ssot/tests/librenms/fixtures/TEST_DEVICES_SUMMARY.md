# LibreNMS Test Devices Summary

This document describes the test devices in `get_librenms_devices.json` to test all functions in `nautobot_ssot/integrations/librenms/utils/__init__.py`.

## Current Test Devices: 25 Total

### Base Devices (Real-world scenarios)
- **Device 1**: `10.0.10.11` (Mikrotik RBwAPG-60ad, routeros OS, network type)
- **Device 2**: `10.0.255.255` (Mikrotik RB5009UPr+S+, routeros OS, network type)

### Hostname Normalization Testing (Devices 3-9)
- **Device 3**: `192.168.1.100` - Tests IP address hostname validation
- **Device 4**: `switch01.company.com` - Tests domain suffix removal and uppercase conversion
- **Device 5**: `FIREWALL01.DOMAIN.LOCAL` - Tests mixed case and multiple domain level removal
- **Device 6**: `router02` / `ROUTER02.SUBDOMAIN.EXAMPLE.COM` - Tests field selection behavior
- **Device 8**: `""` (empty) - Tests missing required fields (hostname, hardware, os, type)
- **Device 9**: `server01` - Tests simple hostname without domain

### Location Validation Testing (Devices 15, 17)
- **Device 15**: `unknown-location` - Tests location validation (GYM location)
- **Device 17**: `valid-city-hall` - Tests valid location validation (GYM location)

### Role Validation Testing (Devices 18-20)
- **Device 18**: `new-role-device` - Tests new role creation (wireless type)
- **Device 19**: `another-new-role` - Tests another new role creation (storage type)
- **Device 20**: `existing-role-device` - Tests existing role validation (network type)

### Manufacturer Validation Testing (Devices 21-24)
- **Device 21**: `unknown-os-device` - Tests unknown OS (unknown_os)
- **Device 22**: `linux-device` - Tests manufacturer creation (linux OS)
- **Device 23**: `unifi-device` - Tests manufacturer creation (unifi OS)
- **Device 24**: `existing-manufacturer-device` - Tests existing manufacturer validation (ios OS)

### Device Type Validation Testing (Devices 25-28)
- **Device 25**: `new-device-type` - Tests new device type creation (New Device Model)
- **Device 26**: `another-new-device-type` - Tests another new device type creation (Another New Model)
- **Device 27**: `existing-device-type` - Tests existing device type validation (WS-C3560-24PS-S)
- **Device 28**: `invalid-manufacturer-device` - Tests device type creation failure (New Model, unknown_os)

### Platform Validation Testing (Devices 29-32)
- **Device 29**: `new-platform` - Tests new platform creation (new_platform_os)
- **Device 30**: `another-new-platform` - Tests another new platform creation (another_new_platform)
- **Device 31**: `existing-platform` - Tests existing platform validation (ios)
- **Device 32**: `invalid-platform-name` - Tests platform creation failure (empty OS)

## Hardware Types Used

### Real-world Hardware
- **RBwAPG-60ad** (Mikrotik)
- **RB5009UPr+S+** (Mikrotik)
- **WS-C3560-24PS-S** (Cisco)
- **WS-C2960-24TC-L** (Cisco)
- **FortiGate-60F** (Fortinet)
- **MX480** (Juniper)
- **Dell PowerEdge R740** (Microsoft)

### Test Hardware (Diverse Names)
- **Wireless Access Point** (Device 18)
- **Network Switch** (Device 20)
- **Unknown Device** (Device 21)
- **Linux Server** (Device 22)
- **UniFi Controller** (Device 23)
- **Cisco Router** (Device 24)
- **New Device Model** (Device 25)
- **Another New Model** (Device 26)
- **New Model** (Device 28)
- **Platform Test Device** (Device 29)
- **Another Platform Device** (Device 30)
- **Existing Platform Device** (Device 31)
- **Invalid Platform Device** (Device 32)

## OS Types Used

### Real-world OS
- **routeros** (Mikrotik)
- **ios** (Cisco)
- **fortios** (Fortinet)
- **junos** (Juniper)
- **windows** (Microsoft)

### Test OS
- **test_os** (multiple devices)
- **unknown_os** (Devices 21, 28)
- **linux** (Devices 22, 26)
- **unifi** (Device 23)
- **new_platform_os** (Device 29)
- **another_new_platform** (Device 30)
- **""** (empty - Devices 8, 32)

## Location Types Used

### Valid Locations
- **City Hall** (majority of devices)
- **GYM** (Devices 15, 17)

## Role Types Used

### Real-world Roles
- **network** (majority of devices)
- **firewall** (Device 5)
- **server** (Device 9)

### Test Roles
- **wireless** (Device 18)
- **storage** (Device 19)
- **test** (multiple devices)
- **""** (empty - Device 8)

## Functions Tested

### `has_required_values()`
- **Device 8**: Multiple missing fields (hostname, hardware, os, type all empty)
- **Tests**: Required field validation failures

### `normalize_device_hostname()`
- **Device 3**: IP address validation (`192.168.1.100`)
- **Device 4**: Domain suffix removal (`switch01.company.com` → `SWITCH01`)
- **Device 5**: Mixed case and domain removal (`FIREWALL01.DOMAIN.LOCAL` → `FIREWALL01`)
- **Device 6**: Field selection behavior (`router02` vs `ROUTER02.SUBDOMAIN.EXAMPLE.COM`)
- **Device 9**: Simple hostname (`server01` → `SERVER01`)
- **Tests**: IP validation, domain removal, case conversion, field selection

### `has_valid_location_data()`
- **Device 15**: Valid location validation (GYM)
- **Device 17**: Valid location validation (GYM)
- **Tests**: Location existence validation

### `has_valid_role()`
- **Device 18**: New role creation (wireless)
- **Device 19**: New role creation (storage)
- **Device 20**: Existing role validation (network)
- **Tests**: Role creation and validation

### `has_valid_manufacturer_data()`
- **Device 21**: Unknown OS (unknown_os)
- **Device 22**: Manufacturer creation (linux → Linux)
- **Device 23**: Manufacturer creation (unifi → Ubiquiti)
- **Device 24**: Existing manufacturer validation (ios → Cisco)
- **Tests**: OS to manufacturer mapping, creation, and validation

### `has_valid_device_type()`
- **Device 25**: New device type creation (New Device Model)
- **Device 26**: New device type creation (Another New Model)
- **Device 27**: Existing device type validation (WS-C3560-24PS-S)
- **Device 28**: Device type creation failure (invalid manufacturer)
- **Tests**: Device type creation, validation, and error handling

### `has_valid_platform()`
- **Device 29**: New platform creation (new_platform_os)
- **Device 30**: New platform creation (another_new_platform)
- **Device 31**: Existing platform validation (ios)
- **Device 32**: Platform creation failure (empty OS)
- **Tests**: Platform creation, validation, and error handling

### `validate_device_data()`
- **All devices**: Complete validation pipeline testing
- **Tests**: Full validation workflow, error aggregation, dependency handling

## Test Coverage Summary

### ✅ Success Scenarios
- Valid hostname normalization (Devices 3-6, 9)
- Valid location validation (Devices 15, 17)
- Valid role validation (Device 20)
- Valid manufacturer validation (Device 24)
- Valid device type validation (Device 27)
- Valid platform validation (Device 31)
- Complete validation pipeline (all devices)

### ✅ Failure Scenarios
- Missing required fields (Device 8)
- Invalid hostname formats (Devices 3-6)
- Unknown OS types (Device 21)
- Invalid manufacturer for device type (Device 28)
- Invalid platform names (Device 32)

### ✅ Creation Scenarios
- New role creation (Devices 18, 19)
- New manufacturer creation (Devices 22, 23)
- New device type creation (Devices 25, 26)
- New platform creation (Devices 29, 30)

### ✅ Integration Testing
- Function dependencies (device type creation depends on manufacturer validation)
- Error collection and deduplication
- Complete validation workflow
- Real-world device configurations

## Test Configuration

The test suite supports testing with:
- Different `hostname_field` values (`"hostname"` vs `"sysName"`)
- Different `librenms_allow_ip_hostnames` settings
- Various location types and role types
- Multiple OS and hardware combinations

## Coverage Assessment: ✅ EXCELLENT

The current test suite of **25 devices** provides comprehensive coverage for all validation functions in the LibreNMS SSoT integration, testing both success and failure scenarios, object creation, and complete integration workflows.

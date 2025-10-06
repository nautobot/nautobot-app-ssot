# normalize_device_hostname Test Devices

This document describes the test devices that test the `normalize_device_hostname` function in `nautobot_ssot/integrations/librenms/utils/__init__.py`.

## Function Overview

The `normalize_device_hostname` function:
1. Checks if the hostname is a valid IP address
2. If it's an IP address, validates against `librenms_allow_ip_hostnames` setting
3. If it's not an IP address, removes domain suffixes and converts to uppercase
4. Returns the normalized hostname as a string

## Test Devices

### Base Devices (Real-world scenarios)
- **Device 1**: `hostname: "10.0.10.11"`, `sysName: "GRCH-AP-P2-UTPO-303-60"` - Tests IP address hostname
- **Device 2**: `hostname: "10.0.255.255"`, `sysName: "GRCH-RT-CORE"` - Tests IP address hostname

### Hostname Normalization Test Devices (3-9)

#### Device 3: IP Address Hostname
- **hostname**: `"192.168.1.100"`
- **sysName**: `"192.168.1.100"`
- **Test Purpose**: Tests IP address validation when `hostname_field` is set to `"hostname"`
- **Expected Result**: 
  - If `librenms_allow_ip_hostnames` is `True`: Returns `"192.168.1.100"`
  - If `librenms_allow_ip_hostnames` is `False`: Returns `None` and adds error

#### Device 4: Domain Suffix Removal
- **hostname**: `"switch01.company.com"`
- **sysName**: `"switch01.company.com"`
- **Test Purpose**: Tests domain suffix removal and uppercase conversion
- **Expected Result**: Returns `"SWITCH01"` (removes `.company.com` and converts to uppercase)

#### Device 5: Mixed Case with Multiple Domain Levels
- **hostname**: `"FIREWALL01.DOMAIN.LOCAL"`
- **sysName**: `"firewall01.domain.local"`
- **Test Purpose**: Tests case conversion and multiple domain level removal
- **Expected Result**: 
  - If using `hostname`: Returns `"FIREWALL01"` (removes `.DOMAIN.LOCAL` and converts to uppercase)
  - If using `sysName`: Returns `"FIREWALL01"` (removes `.domain.local` and converts to uppercase)

#### Device 6: Simple Hostname vs Complex sysName
- **hostname**: `"router02"`
- **sysName**: `"ROUTER02.SUBDOMAIN.EXAMPLE.COM"`
- **Test Purpose**: Tests different behavior based on which field is used as `hostname_field`
- **Expected Result**:
  - If using `hostname`: Returns `"ROUTER02"` (converts to uppercase)
  - If using `sysName`: Returns `"ROUTER02"` (removes `.SUBDOMAIN.EXAMPLE.COM` and converts to uppercase)

#### Device 8: Empty Hostname (Required Values Testing)
- **hostname**: `""` (empty string)
- **sysName**: `""` (empty string)
- **Test Purpose**: Tests missing required fields (handled by `has_required_values`)
- **Expected Result**: Function should not be called due to required values validation failure

#### Device 9: Simple Hostname (No Domain)
- **hostname**: `"server01"`
- **sysName**: `"server01"`
- **Test Purpose**: Tests simple hostname without domain suffix
- **Expected Result**: Returns `"SERVER01"` (converts to uppercase)

## Test Scenarios Covered

### IP Address Validation
- ✅ Valid IPv4 addresses (devices 1, 2, 3)
- ✅ IP address validation against `librenms_allow_ip_hostnames` setting
- ✅ Error handling when IP hostnames are not allowed

### Domain Suffix Removal
- ✅ Single domain suffix (device 4: `.company.com`)
- ✅ Multiple domain levels (device 5: `.domain.local`, device 6: `.subdomain.example.com`)
- ✅ No domain suffix (device 9)

### Case Conversion
- ✅ Lowercase to uppercase conversion (devices 4, 9)
- ✅ Mixed case to uppercase conversion (device 5)
- ✅ Already uppercase preservation (device 6 hostname)

### Field Selection Testing
- ✅ Different behavior when `hostname_field` is set to `"hostname"` vs `"sysName"`
- ✅ Both fields can be used as the source for normalization

### Required Values Integration
- ✅ Empty hostname handling (device 8)
- ✅ Integration with `has_required_values` function

## Expected Function Behavior

For each device, the function should:

1. **Check if hostname is IP address**:
   - If yes: Validate against `librenms_allow_ip_hostnames` setting
   - If no: Proceed to domain removal and case conversion

2. **Remove domain suffixes**:
   - Split on `.` and take first part
   - Handle multiple domain levels correctly

3. **Convert to uppercase**:
   - Apply `.upper()` to the hostname part

4. **Return as string**:
   - Convert final result to string type

## Testing Configuration

To test these devices, you can configure the job with:
- `hostname_field = "hostname"` or `hostname_field = "sysName"`
- `librenms_allow_ip_hostnames = True` or `False`

This allows testing both IP address validation scenarios and domain suffix removal scenarios.

## Integration with validate_device_data

The `normalize_device_hostname` function is called as part of the `validate_device_data` pipeline:

```python
if has_required_values(device, job):
    validated_device["name"] = normalize_device_hostname(device, job)
    # ... other validations
```

This ensures that:
- Hostname normalization only occurs after required values validation
- The normalized hostname is stored in `validated_device["name"]`
- Any errors from hostname normalization cause the function to return `None`

## Coverage Assessment: ✅ COMPREHENSIVE

The current test suite provides comprehensive coverage for the `normalize_device_hostname` function, testing:
- ✅ IP address validation scenarios
- ✅ Domain suffix removal scenarios
- ✅ Case conversion scenarios
- ✅ Field selection scenarios
- ✅ Error handling scenarios
- ✅ Integration with the validation pipeline

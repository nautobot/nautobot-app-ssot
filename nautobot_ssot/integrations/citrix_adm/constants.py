# pylint: disable=duplicate-code
"""Constants for use within Nautobot SSoT for Citrix ADM."""

DEVICETYPE_MAP = {"nsvpx": "NetScaler ADC VPX"}

SCOPED_FIELDS_MAPPING = {
    "dcim.device": [
        "name",
        "device_type",
        "role",
        "serial",
        "location",
        "status",
        "tenant",
        "software_version",
        "ha_node",
    ],
    "dcim.interface": [
        "name",
        "device",
        "status",
        "description",
    ],
    "dcim.location": [
        "name",
        "region",
        "latitude",
        "longitude",
    ],
    "ipam.prefix": [
        "prefix",
        "namespace",
        "tenant",
    ],
    "ipam.ipaddress": [
        "host_address",
        "mask_length",
        "prefix",
        "tenant",
        "tags",
    ],
    "dcim.softwareimagefile": [
        "software_version",
        "image_file_name",
        "platform",
        "status",
        "image_file_size",
        "device_types",
        "download_url",
        "image_file_checksum",
        "hashing_algorithm",
        "default_image",
        "tags",
    ],
    "dcim.softwareversion": [
        "version",
        "platform",
        "alias",
        "release_date",
        "end_of_support_date",
        "status",
        "long_term_support",
        "pre_release",
        "documentation_url",
        "tags",
    ],
    # Add other mappings as needed...
}

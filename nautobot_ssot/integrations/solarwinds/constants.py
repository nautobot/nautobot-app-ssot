"""Constants to be used with SolarWinds SSoT."""

ETH_INTERFACE_NAME_MAP = {
    "AppGigabitEthernet": "virtual",
    "FastEthernet": "100base-tx",
    "GigabitEthernet": "1000base-t",
    "FiveGigabitEthernet": "5gbase-t",
    "TenGigabitEthernet": "10gbase-t",
    "TwentyFiveGigE": "25gbase-x-sfp28",
    "FortyGigabitEthernet": "40gbase-x-qsfpp",
    "FiftyGigabitEthernet": "50gbase-x-sfp28",
    "HundredGigE": "100gbase-x-qsfp28",
}

ETH_INTERFACE_SPEED_MAP = {
    "100Mbps": "100base-tx",
    "1Gbps": "1000base-t",
    "5Gbps": "5gbase-t",
    "10Gbps": "10gbase-t",
    "25Gbps": "25gbase-x-sfp28",
    "40Gbps": "40gbase-x-qsfpp",
    "50Gbps": "50gbase-x-sfp28",
    "100Gbps": "100gbase-x-qsfp28",
}

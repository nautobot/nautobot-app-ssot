"""Storage of data that will not change throughout the life cycle of the application."""

ARISTA_PLATFORM = "arista.eos.eos"
CLOUDVISION_PLATFORM = "Arista EOS-CloudVision"
DEFAULT_APPLY_IMPORT_TAG = False
DEFAULT_CREATE_CONTROLLER = False
DEFAULT_CVAAS_URL = "https://www.arista.io"
DEFAULT_DELETE_DEVICES_ON_SYNC = False
DEFAULT_DEVICE_ROLE = "network"
DEFAULT_DEVICE_ROLE_COLOR = "ff0000"
DEFAULT_DEVICE_STATUS = "cloudvision_imported"
DEFAULT_DEVICE_STATUS_COLOR = "ff0000"
DEFAULT_IMPORT_ACTIVE = False
DEFAULT_SITE = "cloudvision_imported"
DEFAULT_VERIFY_SSL = True

PORT_TYPE_MAP = {
    "xcvr1000BaseT": "1000base-t",
    "xcvr10GBaseSr": "10gbase-x-xfp",
    "xcvr10GBaseLr": "10gbase-x-xfp",
    "xcvr10GBaseT": "10gbase-t",
    "1000BASE-SX": "1000base-x-gbic",
    "1000BASE-LX": "1000base-x-gbic",
    "1000BASE-T": "1000base-t",
    "10GBASE-T": "10gbase-t",
    "10GBASE-MRA-T": "10gbase-t",
    "10GBASE-CR": "10gbase-cx4",
    "10GBASE-CR (QSFP+)": "10gbase-cx4",
    "10GBASE-AOC": "10gbase-x-xfp",
    "10GBASE-SR": "10gbase-x-xfp",
    "10GBASE-SRL": "10gbase-x-xfp",
    "10GBASE-LR": "10gbase-x-xfp",
    "10GBASE-LRL": "10gbase-x-xfp",
    "10GBASE-ER": "10gbase-x-sfpp",
    "10GBASE-ERLBD": "10gbase-x-sfpp",
    "10GBASE-ERBD": "10gbase-x-sfpp",
    "10GBASE-ZR": "10gbase-x-sfpp",
    "10GBASE-DWDM": "10gbase-x-x2",
    "25GBASE-CR": "25gbase-x-sfp28",
    "25GBASE-CR (QSFP)": "25gbase-x-sfp28",
    "25GBASE-AOC": "25gbase-x-sfp28",
    "25GBASE-SR": "25gbase-x-sfp28",
    "25GBASE-MR-SR": "25gbase-x-sfp28",
    "25GBASE-MR-XSR": "25gbase-x-sfp28",
    "25GBASE-LR": "25gbase-x-sfp28",
    "25GBASE-MR-LR": "25gbase-x-sfp28",
    "40GBASE-CR4": "40gbase-x-qsfpp",
    "40GBASE-AOC": "40gbase-x-qsfpp",
    "40GBASE-SR4": "40gbase-x-qsfpp",
    "40GBASE-XSR4": "40gbase-x-qsfpp",
    "40GBASE-BIDI": "40gbase-x-qsfpp",
    "40GBASE-LR4": "40gbase-x-qsfpp",
    "40GBASE-LRL4": "40gbase-x-qsfpp",
    "40GBASE-PLRL4": "40gbase-x-qsfpp",
    "40GBASE-PLR4": "40gbase-x-qsfpp",
    "40GBASE-ER4": "40gbase-x-qsfpp",
    "100GBASE-CR4": "100gbase-x-cfp4",
    "100GBASE-AOC": "100gbase-x-qsfp28",
    "100GBASE-SR4": "100gbase-x-qsfp28",
    "100GBASE-XSR4": "100gbase-x-qsfp28",
    "100GBASE-SWDM4": "100gbase-x-qsfp28",
    "100GBASE-BIDI": "100gbase-x-qsfp28",
    "100GBASE-PSM4": "100gbase-x-qsfp28",
    "100GBASE-PLRL4": "100gbase-x-qsfp28",
    "100GBASE-LR4": "100gbase-x-qsfp28",
    "100GBASE-LRL4": "100gbase-x-qsfp28",
    "100GBASE-CWDM4": "100gbase-x-qsfp28",
    "100GBASE-XCWDM4": "100gbase-x-qsfp28",
    "100GBASE-ERL4": "100gbase-x-qsfp28",
    "100GBASE-ZR4": "100gbase-x-qsfp28",
    "100GBASE-DR": "100gbase-x-qsfp28",
    "100GBASE-FR": "100gbase-x-qsfp28",
    "100GBASE-LR": "100gbase-x-qsfp28",
    "200GBASE-CR4": "200gbase-x-cfp2",
    "200GBASE-AOC": "200gbase-x-qsfp56",
    "200GBASE-SR4": "200gbase-x-qsfp56",
    "200GBASE-FR4": "200gbase-x-qsfp56",
    "400GBASE-CR8": "400gbase-x-qsfpdd",
    "400GBASE-AOC": "400gbase-x-qsfpdd",
    "400GBASE-SR8": "400gbase-x-qsfpdd",
    "400GBASE-SR8-C": "400gbase-x-qsfpdd",
    "400GBASE-DR4": "400gbase-x-qsfpdd",
    "400GBASE-XDR4": "400gbase-x-qsfpdd",
    "400GBASE-PLR4": "400gbase-x-qsfpdd",
    "400GBASE-FR4": "400gbase-x-qsfpdd",
    "400GBASE-LR4": "400gbase-x-qsfpdd",
    "400GBASE-2FR4": "400gbase-x-osfp",
    "400GBASE-ZR": "400gbase-x-qsfpdd",
}

"""General utils for IPFabric."""

import re

from nautobot_ssot.integrations.ipfabric.constants import DEFAULT_INTERFACE_TYPE


VIRTUAL = "virtual"
BRIDGE = "bridge"
LAG = "lag"

GBIC = "gbic"
SFP = "sfp"
LR = "lr"
SR = "sr"
SX = "sx"
LX = "lx"
XFP = "xfp"
X2 = "x2"
XENPAK = "xenpak"
QSFP = "qsfp"

HUNDRED_MEG = "100m"
HUNDRED_MEG_BASE = "100base"
GIG = "1g"
GIG_BASE = "1000base"
RJ45 = "rj45"
TWO_AND_HALF_GIG_BASE = "2.5gbase"
FIVE_GIG_BASE = "5gbase"
TEN_GIG = "10g"
TEN_GIG_BASE_T = "10gbaset"
TWENTY_FIVE_GIG = "25g"
FORTY_GIG = "40g"
FIFTY_GIG = "50g"
HUNDRED_GIG = "100g"
TWO_HUNDRED_GIG = "200g"
FOUR_HUNDRED_GIG = "400g"
EIGHT_HUNDRED_GIG = "800g"


def convert_media_type(  # pylint: disable=too-many-return-statements,too-many-branches,too-many-statements
    media_type: str,
    interface_name: str,
) -> str:
    """Convert provided `media_type` to value used by Nautobot.

    Args:
        media_type: The media type of an inteface (i.e. SFP-10GBase)
        interface_name: The name of the interface with `media_type`.

    Returns:
        str: The corresponding represention of `media_type` in Nautobot.
    """
    if media_type:
        media_type = media_type.lower().replace("-", "")
        if VIRTUAL in media_type:
            return VIRTUAL
        if BRIDGE in media_type:
            return BRIDGE
        if LAG in media_type:
            return LAG

        if TEN_GIG_BASE_T in media_type:
            return "10gbase-t"

        # Going from 10Gig to lower bandwidths to allow media that supports multiple
        # bandwidths to use highest supported bandwidth
        if TEN_GIG in media_type:
            nautobot_media_type = "10gbase-x-"
            if XFP in media_type:
                nautobot_media_type += "xfp"
            elif X2 in media_type:
                nautobot_media_type += "x2"
            elif XENPAK in media_type:
                nautobot_media_type += "xenpak"
            else:
                nautobot_media_type += "sfpp"
            return nautobot_media_type

        # Flipping order of 5gig and 2.5g as both use the string 5gbase
        if TWO_AND_HALF_GIG_BASE in media_type:
            return "2.5gbase-t"

        if FIVE_GIG_BASE in media_type:
            return "5gbase-t"

        if GIG_BASE in media_type or RJ45 in media_type or GIG in media_type:
            nautobot_media_type = "1000base-"
            if GBIC in media_type:
                nautobot_media_type += "x-gbic"
            elif SFP in media_type or SR in media_type or LR in media_type or SX in media_type or LX in media_type:
                nautobot_media_type += "x-sfp"
            else:
                nautobot_media_type += "t"
            return nautobot_media_type

        if HUNDRED_MEG_BASE in media_type or HUNDRED_MEG in media_type:
            return "100base-tx"

        if TWENTY_FIVE_GIG in media_type:
            return "25gbase-x-sfp28"

        if FORTY_GIG in media_type:
            return "40gbase-x-qsfpp"

        if FIFTY_GIG in media_type:
            return "50gbase-x-sfp56"

        if HUNDRED_GIG in media_type:
            nautobot_media_type = "100gbase-x-"
            if QSFP in media_type:
                nautobot_media_type += "qsfp28"
            else:
                nautobot_media_type += "cfp"
            return nautobot_media_type

        if TWO_HUNDRED_GIG in media_type:
            nautobot_media_type = "200gbase-x-"
            if QSFP in media_type:
                nautobot_media_type += "qsfp56"
            else:
                nautobot_media_type += "cfp2"
            return nautobot_media_type

        if FOUR_HUNDRED_GIG in media_type:
            nautobot_media_type = "400gbase-x-"
            if QSFP in media_type:
                nautobot_media_type += "qsfp112"
            else:
                nautobot_media_type += "osfp"
            return nautobot_media_type

        if EIGHT_HUNDRED_GIG in media_type:
            nautobot_media_type = "800gbase-x-"
            if QSFP in media_type:
                nautobot_media_type += "qsfpdd"
            else:
                nautobot_media_type += "osfp"
            return nautobot_media_type
    else:
        interface_name = interface_name.lower()
        regex_to_type = (
            (r"po(rt-?channel)?\d", "lag"),
            (r"vl(an)?\d", "virtual"),
            (r"lo(opback)?\d", "virtual"),
            (r"tu(nnel)?\d", "virtual"),
            (r"vx(lan)?\d", "virtual"),
            (r"fa(stethernet)?\d", "100base-tx"),
            (r"gi(gabitethernet)?\d", "1000base-t"),
            (r"te(ngigabitethernet)?\d", "10gbase-x-sfpp"),
            (r"twentyfivegigabitethernet\d", "25gbase-x-sfp28"),
            (r"fo(rtygigabitethernet)?\d", "40gbase-x-qsfpp"),
            (r"fi(ftygigabitethernet)?\d", "50gbase-x-sfp56"),
            (r"hu(ndredgigabitethernet)?\d", "100gbase-x-qsfp28"),
            (r"twohundredgigabitethernet\d", "200gbase-x-qsfp56"),
        )
        for regex, iface_type in regex_to_type:
            if re.match(regex, interface_name):
                return iface_type

    return DEFAULT_INTERFACE_TYPE

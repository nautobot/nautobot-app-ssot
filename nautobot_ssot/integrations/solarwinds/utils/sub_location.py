"""Hostname-driven sub-location derivation for the SolarWinds SSoT integration.

The behavior is fully driven by an operator-supplied mapping (the Job's
``sub_location_map`` input). See
``docs/user/integrations/solarwinds_sub_location_mapping.md`` for the schema and
worked examples.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def derive_sub_location(
    hostname: str,
    location_name: Optional[str],
    mapping: Optional[dict],
) -> Optional[str]:
    """Return a sub-location name derived from a device's hostname.

    The resolution pipeline is:

    1. If ``mapping`` has no entry for ``location_name``, return ``None``.
    2. If any ``overrides`` substring is present in the hostname, return the
       mapped sub-location name verbatim.
    3. Try each regex in ``patterns`` (in order). The first capturing group of
       the first matching pattern is taken. Numeric captures are zero-padded to
       two characters; alphabetic captures are uppercased.
    4. If nothing matches, return ``None`` so the device stays at its parent.

    Args:
        hostname: The device hostname; matching is performed against the
            uppercased value.
        location_name: The parent location name the device belongs to, used as
            the mapping key.
        mapping: The user-supplied mapping from the Job input.

    Returns:
        The derived sub-location name, or ``None`` if the mapping is missing
        for the location or no rule produced a value.
    """
    if not mapping or not location_name:
        return None
    rules = mapping.get(location_name)
    if not rules:
        return None

    upper_hostname = hostname.upper()

    for substring, value in (rules.get("overrides") or {}).items():
        if substring.upper() in upper_hostname:
            return value

    prefix = rules.get("prefix", "")
    for pattern in rules.get("patterns") or []:
        try:
            match = re.search(pattern, upper_hostname)
        except re.error as error:
            logger.warning(
                "Invalid regex %r in sub_location_map[%s]: %s",
                pattern,
                location_name,
                error,
            )
            continue
        if not match or not match.groups():
            continue
        captured = match.group(1)
        if captured.isdigit():
            return f"{prefix}{int(captured):02d}"
        return f"{prefix}{captured.upper()}"

    return None

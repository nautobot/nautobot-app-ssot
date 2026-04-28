#!/usr/bin/env python3
"""
Prepare a CSV file for Nautobot Device Onboarding.

This script expects a UTF-8 CSV input file like `cuk_devices_v1_1.csv`and
outputs cleaned and transformed onboarding-ready UTF-8 CSV files, split by
namespace and platform_name combinations.
"""

import argparse
import csv
import os
import re
import sys
from collections import defaultdict

# Constants
DECK_RETURN_PREFIX = "Deck_"
FLOOR_RETURN_PREFIX = "Floor_"
LEVEL_RETURN_PREFIX = "Level_"
EXPECTED_EMPTY = ["device_role_name", "location_name"]
MAKE_EMPTY = ["platform_name"]
# TODO: Could consider grabbing this list of valid roles from Nautobot dynamically, one day
CANONICAL_ROLES = {
    'SPNS', 'DSPS', 'BSPS', 'SVLS', 'BDLS', 'EDSP', 'ENLS', 'DSLS',
    'ACLS', 'INTS', 'WANS', 'DMZS', 'NGFW', 'DIST', 'CORE', 'CEXT',
    'ACCS', 'STLK', 'CBAS', 'WLCS', 'OBSW', 'OBFW', 'OBMC', 'DNAC',
    'TVCS', 'TVDS', 'TVAS', 'CCTV', 'ENAS', 'TORS', 'CHKS', 'PBXS',
    'VSAT',
}
GENERIC_ROLE_ALIASES = {
    'CCS': 'CBAS',
    'CAS': 'CBAS',
    'PCS': 'CBAS',
    'WETLOCKER': 'CBAS',
    'WET_LOCKER': 'CBAS',
    'VSW': 'VSAT',
    'ACC': 'ACCS',
    'QSR': 'ACCS',
    'PBX': 'PBXS',
    'UC': 'PBXS',
    'CVGW': 'PBXS',
    'CHK': 'CHKS',
    'LES': 'ENAS',
    'BCC': 'ENAS',
    'IDF': 'DIST',
    'WAN': 'WANS',
    'PEP': 'INTS',
    'STL': 'STLK',
    'TOR': 'TORS',
}
QUEEN_ANNE_ROLE_ALIASES = {
    'AC': 'ACCS',
    'XX': 'CBAS',
    'BL': 'BDLS',
    'MD': 'WLCS',
    'TL': 'SVLS',
    'DL': 'DSLS',
    'WA': 'WANS',
    'PEPLINK': 'INTS',
}
ALL_OFFICES = {
    'Carnival House', 'Hamburg', 'Mumbai', 'Hounslow', 'Dance Academy',
}
ALL_TERMINALS = {
    'Ocean Terminal', 'Mayflower Terminal',
}
# TODO: Eventually we may want to reduce this. It skips records for platforms we don't want
PLATFORM_NAME_EXCLUDE_LIST = [
    "BIG-IP Virtual Edition",
    "Cisco Meraki MS210-48",
    "Cisco",  # Generic entry, too vague
    "Data Domain dd670",
    "Data Domain, Inc",
    "DataDomain 2500",
    "GS108Tv2 Smart Switch",
    "H3C 5130-24G-PoE+-2SFP+-2XGT (370W) EI",
    "H3C",
    "M-300",
    "Meraki Networks, Inc.",
    "NetBotz 455 Wall",
    "Nexus 93108TC-FX",  # Cisco NX-OS, not IOS/IOS-XE
    "PA-3410",  # Palo Alto, in scope later but not now
    "PA-3430",  # Palo Alto, in scope later but not now
    "PA-445",  # Palo Alto, in scope later but not now
    "PA-5250",  # Palo Alto, in scope later but not now
    "PA-820",  # Palo Alto, in scope later but not now
    "PePLink Ltd.",
    "Unknown",
    "Windows 2008 R2 Server",
]
# TODO: Eventually we want to remove this. It skips records for ships we can't poll directly
NAMESPACE_EXCLUDE_LIST = [
    "Arvia",
    "Iona",
    "Queen Anne",
]

def sanitize_filename(text):
    """
    Sanitize a string to be safe for use in a filename.
    Replaces spaces and special characters with underscores.
    """
    # Replace spaces and special characters with underscores
    sanitized = re.sub(r'[^\w\-.]', '_', text)
    # Remove consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    return sanitized if sanitized else 'unknown'

def extract_floor_level_deck_handling_edge_cases(hostname, location=None):
    """
    Return floor/level/deck identifier from hostname
    """
    hostname = hostname.upper()

    # Decide parsing + return prefixes based on location
    if location in ALL_OFFICES:
        search_prefix = "LV"
        return_prefix = FLOOR_RETURN_PREFIX
    elif location in ALL_TERMINALS:
        search_prefix = "LV"
        return_prefix = LEVEL_RETURN_PREFIX
    else:
        search_prefix = "DK"
        return_prefix = DECK_RETURN_PREFIX

    if location == "Queen Anne":
        if "CR" in hostname:
            return f"{return_prefix}02"
        if "BC" in hostname:
            return f"{return_prefix}06"

    if re.search(r'PO[A-Z]{2}IT[A-Z]*(\d{3})$', hostname):
        match = re.search(r'PO[A-Z]{2}IT[A-Z]*(\d+)$', hostname)
        if match:
            digits = match.group(1)
            level = int(digits[-2:])
            return f"{return_prefix}{level:02d}"

    match = re.search(
        rf'{search_prefix}0?([A-Z]|\d{{1,2}})',
        hostname,
        re.IGNORECASE
    )
    if not match:
        return None

    value = match.group(1).upper()

    if value.isdigit():
        return f"{return_prefix}{int(value):02d}"

    return f"{return_prefix}{value}"

# pylint: disable=too-many-return-statements, too-many-branches
def extract_role_handling_edge_cases(hostname, ship=None):
    """
    Return canonical device role from hostname using CANONICAL_ROLES first,
    then ROLE_ALIASES as fallback. Returns None if nothing matches.

    Also handle required edge cases.
    """
    hostname = hostname.upper()

    if ship == "Queen Anne":
        for alias, canonical_mapping in QUEEN_ANNE_ROLE_ALIASES.items():
            if alias in hostname:
                return canonical_mapping

    if re.search(r'PO[A-Z]{2}IT[A-Z]*(\d{3})$', hostname):
        if "CORE" in hostname:
            return "TVCS"
        if "DIST" in hostname:
            return "TVDS"
        # TODO: See Jira - ideally based on port count some should be CBAS not ACCS
        return "ACCS"

    for role in CANONICAL_ROLES:
        if role in hostname:

            # ROLE EXCEPTIONS
            if role == "CORE" and "VOD" in hostname:
                return "TVCS"
            if role == "ACCS" and "VOD" in hostname:
                return "TVAS"

            return role

    for alias, canonical_mapping in GENERIC_ROLE_ALIASES.items():
        if alias in hostname:

            # ROLE EXCEPTIONS
            if alias == "TOR" and ship in {"Queen Anne", "Iona"}:
                return "SLVS"

            return canonical_mapping

    return None

# pylint: disable=too-many-locals, too-many-statements
def transform_csv(input_file, output_path, rejected_file, debug=False):
    """Clean and transform CSV data."""
    try:
        with open(input_file, "r", encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            fieldnames = reader.fieldnames

            # Group rows by namespace and platform_name
            grouped_rows = defaultdict(list)
            rejected_rows = []
            one_of_each_type = {}

            for row in reader:
                hostname = row.get('hostname', '')
                namespace = row.get('namespace', '')
                platform_name = row.get('platform_name', '')

                # Warn if values will be overwritten
                for val_to_check in EXPECTED_EMPTY:
                    if row.get(val_to_check) != '':
                        print(
                            f"WARNING: Replacing data in '{val_to_check}' for '{hostname}'",
                            file=sys.stderr
                        )
                    row[val_to_check] = ''

                # Remove values that we don't want
                for val_to_check in MAKE_EMPTY:
                    row[val_to_check] = ''

                changes = []

                # Set location_parent_name
                row['location_parent_name'] = namespace
                changes.append(
                    f"location_parent_name: '{namespace}'"
                )

                # If this is an office or terminal, override namespace column in the CSV to 'Global'
                if namespace in ALL_OFFICES or namespace in ALL_TERMINALS:
                    row['namespace'] = 'Global'

                # Extract and set location_name
                extracted_fld = extract_floor_level_deck_handling_edge_cases(hostname, namespace)
                if extracted_fld:
                    row['location_name'] = extracted_fld
                    changes.append(
                        f"location_name: '{extracted_fld}'"
                    )

                # Extract and set device role
                extracted_role = extract_role_handling_edge_cases(hostname, namespace)
                if extracted_role:
                    row['device_role_name'] = extracted_role
                    changes.append(
                        f"device_role_name: '{extracted_role}'"
                    )

                # Print changes to stderr
                if changes:
                    print(f"CHANGED: {hostname} | {' | '.join(changes)}", file=sys.stderr)

                # Add this row to the appropriate output
                if not extracted_fld or not extracted_role or \
                    platform_name in PLATFORM_NAME_EXCLUDE_LIST or \
                    namespace in NAMESPACE_EXCLUDE_LIST:
                    reject_criteria = []
                    if not extracted_fld:
                        reject_criteria.append("floor/level/deck")
                    if not extracted_role:
                        reject_criteria.append("role")
                    if platform_name in PLATFORM_NAME_EXCLUDE_LIST:
                        reject_criteria.append("exclude_listed_platform")
                    if namespace in NAMESPACE_EXCLUDE_LIST:
                        reject_criteria.append("exclude_listed_namespace")
                    row['rejection_criteria'] = reject_criteria
                    rejected_rows.append(row)
                    print(
                        f"WARNING: Couldn't parse '{', '.join(reject_criteria)}' from '{hostname}'",
                        file=sys.stderr
                    )
                else:
                    # Group by namespace and platform_name
                    group_key = (namespace, platform_name)
                    grouped_rows[group_key].append(row)

                    # Track one of each platform_name for debug mode
                    if debug and platform_name not in one_of_each_type:
                        one_of_each_type[platform_name] = row.copy()

            output_fieldnames = list(fieldnames)

            output_fieldnames.remove('hostname')

            # Add location_parent_name to fieldnames for output
            output_fieldnames.append("location_parent_name")

            # Handle debug mode
            if debug:
                debug_folder = os.path.join(output_path, "debug")
                os.makedirs(debug_folder, exist_ok=True)
                debug_filename = os.path.join(debug_folder, "one_of_each_type.csv")

                debug_rows = list(one_of_each_type.values())
                for row in debug_rows:
                    row.pop('hostname', None)

                with open(debug_filename, 'w', encoding='utf-8') as outfile:
                    writer = csv.DictWriter(outfile, fieldnames=output_fieldnames)
                    writer.writeheader()
                    writer.writerows(debug_rows)

                print(f"Created: {debug_filename} ({len(debug_rows)} rows)", file=sys.stderr)
                return

            # Output successfully processed records to separate files per group
            for (namespace, platform_name), rows in grouped_rows.items():
                # Create sanitized folder and filename
                sanitized_ns = sanitize_filename(namespace)
                sanitized_plt = sanitize_filename(platform_name) if platform_name else 'no_platform'

                # Create namespace folder if it doesn't exist
                namespace_folder = os.path.join(output_path, sanitized_ns)
                os.makedirs(namespace_folder, exist_ok=True)

                # Create output filename in namespace folder
                output_filename = os.path.join(namespace_folder, f"{sanitized_plt}.csv")

                for row in rows:
                    row.pop('hostname', None)

                with open(output_filename, 'w', encoding='utf-8') as outfile:
                    writer = csv.DictWriter(outfile, fieldnames=output_fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)

                print(f"Created: {output_filename} ({len(rows)} rows)", file=sys.stderr)

            # Output rejected records to rejected_file
            reject_fieldnames = list(fieldnames)
            reject_fieldnames.append("location_parent_name")
            reject_fieldnames.append("rejection_criteria")

            with open(rejected_file, 'w', encoding='utf-8') as rejectfile:
                writer = csv.DictWriter(rejectfile, fieldnames=reject_fieldnames)
                writer.writeheader()
                writer.writerows(rejected_rows)

    except FileNotFoundError:
        print(f"ERROR: File '{input_file}' not found", file=sys.stderr)
        sys.exit(1)
    except PermissionError:
        print(f"ERROR: Permission denied for file '{input_file}'", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prepare a CSV file for the Nautobot Device Onboarding app."
    )
    parser.add_argument(
        "input_file",
        help="Path to input UTF-8 CSV file for parsing"
    )
    parser.add_argument(
        "output_path",
        help="Directory path for output CSV files (will create namespace subdirectories)"
    )
    parser.add_argument(
        "reject_file",
        help="Path to output UTF-8 CSV file for rejects (with rejection_criteria column)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help='If set, output just one record per platform_name to a single CSV in "debug" folder'
    )

    args = parser.parse_args()

    transform_csv(
        args.input_file,
        args.output_path,
        args.reject_file,
        debug=args.debug
    )

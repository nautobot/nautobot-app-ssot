# SolarWinds Sub-Location Mapping

The SolarWinds SSoT Job can place each synchronized device under a *sub-location*
of its parent container (e.g. floor, deck, row, level) instead of attaching it
directly to the parent. The behavior is driven entirely by a JSON Job input —
no hostname-parsing logic is hard-coded in the integration.

This document explains the shape of that mapping, how each field is used, and
how to adapt it to environments that do not match the original Carnival /
cruise-ship use case.

## When to use this

Use the sub-location mapping when:

- Devices share a single parent location in SolarWinds (e.g. a building, a
  campus, a ship), but you want them organized in Nautobot under finer-grained
  sub-locations.
- The sub-location identity can be *derived from the hostname* via a regex or
  via a known set of substring overrides.

If the sub-location identity lives outside the hostname (e.g. only in a custom
SolarWinds property), this mapping will not help — you would need a different
extension.

## Mapping shape

```json
{
  "<Parent Location Name>": {
    "patterns": ["<regex with one capture group>", "..."],
    "prefix": "<string>",
    "overrides": {"<hostname substring>": "<full sub-location name>"}
  }
}
```

Top-level keys are parent location names. Each value is a rule object with up
to three fields, described below. Locations that do **not** appear as a key are
skipped — devices in them stay attached directly to the parent.

### Field reference

| Field | Required | Role | Matched/produced against |
|---|---|---|---|
| **key** | yes | The **parent location name** in Nautobot. Must match the container the device currently lives in. | Compared (case-sensitive) to the device's parent container/location name. |
| **`patterns`** | yes | List of regexes that **extract a token from the hostname**. Each regex must have exactly one capturing group. The first regex that matches wins. | Run against the hostname (uppercased). |
| **`prefix`** | yes | String prepended to the captured token to **build the sub-location name** that will be created in Nautobot under the parent. | Output: `f"{prefix}{captured_token}"`. |
| **`overrides`** | no | `{hostname-substring: full-sub-location-name}`. Short-circuits the regex when a substring is found in the hostname. Useful for hostnames that the regex cannot reach. | Substring (case-insensitive) tested against the hostname. |

### Resolution pipeline

```
device.hostname + device.parent_location
        │
        ▼
  look up parent_location in mapping  ──── not present ──► no sub-location
        │
        ▼
  any override substring in hostname? ──── yes ──► return that exact value
        │
        ▼
  try each pattern regex; first match's capture group + prefix
        │
        ▼
  no match ──► no sub-location
```

### Output formatting

- If the captured token consists entirely of digits, it is zero-padded to two
  characters: `f"{prefix}{int(token):02d}"` (e.g. `Floor_03`).
- Otherwise the token is uppercased and concatenated as-is:
  `f"{prefix}{TOKEN.upper()}"` (e.g. `Deck_A`).

## Examples

### Hospital with buildings and floors

Parent locations in Nautobot: `Tower A`, `Tower B`. Hostnames look like
`TOWA-FL03-SW01`, `TOWB-F12-AP07`.

```json
{
  "Tower A": {
    "patterns": ["FL?(\\d{1,2})"],
    "prefix": "Floor_"
  },
  "Tower B": {
    "patterns": ["FL?(\\d{1,2})"],
    "prefix": "Floor_"
  }
}
```

`TOWA-FL03-SW01` at parent `Tower A` → captures `03` → device is placed under
sub-location **`Floor_03`** of `Tower A`.

### Data center with rows and racks

Parent locations: `DC-Frankfurt`, `DC-Ashburn`. Hostnames: `FRA-R12-A05-LEAF1`.
You want to nest devices under the row.

```json
{
  "DC-Frankfurt": {"patterns": ["R(\\d{1,2})"], "prefix": "Row_"},
  "DC-Ashburn":   {"patterns": ["R(\\d{1,2})"], "prefix": "Row_"}
}
```

`FRA-R12-A05-LEAF1` → `Row_12` under `DC-Frankfurt`.

### Mixed conventions plus a known special case

A retail HQ where most APs encode the floor as `LV04`, a legacy batch encodes
it as the trailing two digits of `IT001`–`IT099`, and one device on the helipad
has no parseable token.

```json
{
  "HQ Building": {
    "patterns": [
      "LV(\\d{1,2})",
      "IT(\\d{2})$"
    ],
    "prefix": "Floor_",
    "overrides": {"HELIPAD": "Roof"}
  }
}
```

- `HQ-LV04-AP1` → `Floor_04`
- `HQ-IT07` → `Floor_07`
- `HQ-HELIPAD-CAM` → `Roof` (override beats regex)
- `HQ-LOBBY-PHONE` → no match → device stays at `HQ Building` (no sub-location)

### Cruise-ship deployment (the original use case)

Ships, offices, and passenger terminals each follow their own convention. Ships
use `DK<n>` for decks, offices use `LV<n>` for floors, and terminals use
`LV<n>` for levels. Two cabins on the *Queen Anne* have to be hard-coded
because their hostnames carry no deck token.

```json
{
  "Arcadia":   {"patterns": ["DK0?([A-Z]|\\d{1,2})"], "prefix": "Deck_"},
  "Britannia": {"patterns": ["DK0?([A-Z]|\\d{1,2})"], "prefix": "Deck_"},
  "Queen Anne": {
    "patterns": ["DK0?([A-Z]|\\d{1,2})"],
    "prefix": "Deck_",
    "overrides": {"CR": "Deck_02", "BC": "Deck_06"}
  },
  "Carnival House": {"patterns": ["LV0?([A-Z]|\\d{1,2})", "PO[A-Z]{2}IT[A-Z]*\\d*(\\d{2})$"], "prefix": "Floor_"},
  "Hamburg":        {"patterns": ["LV0?([A-Z]|\\d{1,2})", "PO[A-Z]{2}IT[A-Z]*\\d*(\\d{2})$"], "prefix": "Floor_"},
  "Mumbai":         {"patterns": ["LV0?([A-Z]|\\d{1,2})", "PO[A-Z]{2}IT[A-Z]*\\d*(\\d{2})$"], "prefix": "Floor_"},
  "Hounslow":       {"patterns": ["LV0?([A-Z]|\\d{1,2})", "PO[A-Z]{2}IT[A-Z]*\\d*(\\d{2})$"], "prefix": "Floor_"},
  "Dance Academy":  {"patterns": ["LV0?([A-Z]|\\d{1,2})", "PO[A-Z]{2}IT[A-Z]*\\d*(\\d{2})$"], "prefix": "Floor_"},
  "Ocean Terminal":     {"patterns": ["LV0?([A-Z]|\\d{1,2})"], "prefix": "Level_"},
  "Mayflower Terminal": {"patterns": ["LV0?([A-Z]|\\d{1,2})"], "prefix": "Level_"}
}
```

Walk-through:

| Hostname | Parent container | Match | Capture | Result |
|---|---|---|---|---|
| `MUM-ESTLV05-ACCS-1` | Mumbai | `LV0?([A-Z]\|\d{1,2})` → `LV05` | `05` | `Floor_05` |
| `CUK-MUM-WAP01-1` | Mumbai | none | — | `None` (stays at Mumbai) |
| `ARC-FZ1DK05-IDF01` | Arcadia | `DK0?([A-Z]\|\d{1,2})` → `DK05` | `05` | `Deck_05` |
| `QA-CR-CAM01` | Queen Anne | override `CR` | — | `Deck_02` |

## Related Job inputs

- **`sub_location_type`** (`LocationType`) — the Nautobot `LocationType` used
  when the integration creates a missing sub-location. The mapping decides
  *what to call* the sub-location; this Job input decides *what type* it has.
  If `sub_location_type` is unset, sub-location resolution is skipped entirely
  regardless of the mapping content.
- **`tenant`** — sub-locations are created without a tenant; the device itself
  inherits the Job's tenant.

## Authoring tips

- Regexes live inside JSON, so backslashes must be escaped (`\\d`, `\\s`).
- Each regex must have exactly **one** capturing group; non-capturing groups
  (`(?:...)`) are fine for grouping without consuming a slot.
- Anchor with `^` / `$` when you need to match a particular position. Hostnames
  are uppercased before matching, so write your patterns in upper case (or use
  the `(?i)` inline flag).
- The first matching regex wins. Order patterns from most-specific to
  least-specific.
- `overrides` always beats `patterns`. Use it sparingly — every override is a
  hostname that your regex *could* be improved to handle.
- A location absent from the mapping is a safe default. Add the location only
  when you actually want sub-location placement for it.

## Limitations

- The mapping only consults the **hostname** and the **parent location name**.
  It cannot reach into other SolarWinds attributes (custom properties, IP,
  vendor, etc.).
- The sub-location is always created as a direct child of the device's current
  parent container. Multi-level nesting (e.g. building → floor → wing) is not
  expressed in this mapping.
- Sub-location names are global within their parent — two patterns producing
  the same `prefix + token` for the same parent will resolve to the same
  Nautobot Location.

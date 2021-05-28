import os

import usaddress
import yaml

from jinja2 import Environment, FileSystemLoader


DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))


def get_nested_attr(obj, attr):
    """Like getattr, but handles nested attributes like "device_type.manufacturer.name".

    Additionally, returns None if no such attribute exists rather than throwing an exception.
    """
    value = obj
    for subattr in attr.split("."):
        if hasattr(value, subattr):
            value = getattr(value, subattr)
        else:
            return None
    return value


def update(target, source):
    """Update the target dictionary with data from source.

    Equivalent to calling target.update(source), but reports whether any changes occurred in target.

    Args:
      target (dict): Dictionary to update
      source (dict): Dictionary whose contents will be set into ``target``.

    Returns:
      bool: True if ``target`` was modified at all.
    """
    changed = False
    for key, value in source.items():
        if key in target:
            if target[key] == value:
                continue  # No change to this key
        target[key] = value
        changed = True

    return changed


def load_yaml_datafile(filename, config):
    """Get the contents of the given YAML datafile.

    Args:
      filename (str): Filename within the ``nautobot_data_sync_servicenow/data/`` directory.
      config (dict): Data for Jinja2 templating.

    Returns:
      object: Parsed and populated data.
    """
    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.isfile(file_path):
        raise RuntimeError(f"No data file found at {file_path}")
    env = Environment(loader=FileSystemLoader(DATA_DIR), autoescape=True)
    template = env.get_template(filename)
    populated = template.render(config)
    return yaml.safe_load(populated)


def parse_physical_address(nb_site, field):
    """Attempt to parse the free-text Nautobot "site.physical_address" into tokens and construct the requested field.

    Args:
      nb_site (Site): Nautobot record that has a "physical_address".
      field (str): Address field to retrieve.
    """
    # usaddress.tag() returns a tuple (data, address_type)
    data, _ = usaddress.tag(nb_site.physical_address)
    if field == "street":
        text = ""
        for key in ("AddressNumber", "StreetName", "StreetNamePostType", "OccupancyType", "OccupancyIdentifier"):
            if key in data:
                if text:
                    text += " "
                text += data[key]
        return text
    if field == "city":
        return data.get("PlaceName", "")
    if field == "state":
        return data.get("StateName", "")
    if field == "zip":
        return data.get("ZipCode", "")
    if field == "country":
        return data.get("CountryName", "")
    raise NotImplementedError

"""Utility functions for working with bootstrap and Nautobot."""

import inspect
import os
from datetime import datetime

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from nautobot.extras.datasources.registry import get_datasource_content_choices
from nautobot.extras.models import Contact, Team
from nautobot.extras.utils import FeatureQuery, RoleModelsQuery, TaggableClassesQuery


def is_running_tests():
    """Check whether running unittests or actual job."""
    for frame in inspect.stack():
        if frame.filename.endswith("unittest/case.py"):
            return True
    return False


def check_sor_field(model):
    """Check if the System of Record field is present and is set to "Bootstrap"."""
    return (
        "system_of_record" in model.custom_field_data
        and model.custom_field_data["system_of_record"] is not None
        and os.getenv("SYSTEM_OF_RECORD", "Bootstrap") in model.custom_field_data["system_of_record"]
    )


def get_sor_field_nautobot_object(nb_object):
    """Get the System of Record field from an object."""
    _sor = ""
    if "system_of_record" in nb_object.custom_field_data:
        _sor = (
            nb_object.custom_field_data["system_of_record"]
            if nb_object.custom_field_data["system_of_record"] is not None
            else ""
        )
    return _sor


def lookup_content_type(content_model_path, content_type):
    """Lookup content type for a GitRepository object."""
    _choices = get_datasource_content_choices(content_model_path)
    _found_type = None
    for _element in _choices:
        if _element[1] == content_type:
            _found_type = _element[0]
            return _found_type
    return None


def lookup_content_type_id(nb_model, model_path):
    """Find ContentType choices for a model path and return the ContentType ID."""
    _choices = FeatureQuery(nb_model).get_choices()
    _found_type = None
    for _element in _choices:
        if _element[0] == model_path:
            _found_type = _element[1]
            return _found_type
    return None


def lookup_content_type_model_path(nb_model, content_id):
    """Find ContentType choices for a model path and return the ContentType ID."""
    _choices = FeatureQuery(nb_model).get_choices()
    _found_type = None
    for _element in _choices:
        if _element[1] == content_id:
            _found_type = _element[0]
            return _found_type
    return None


def lookup_tag_content_type_model_path(content_id):
    """Find model paths for a given ContentType ID for Tag Objects."""
    _content_type = ContentType.objects.get(id=content_id)
    return f"{_content_type.model}.{_content_type.name.replace(' ', '')}"


def lookup_model_for_taggable_class_id(content_id):
    """Find a model path for a given ContentType ID."""
    _choices = TaggableClassesQuery().get_choices()
    _found_type = None
    for _element in _choices:
        if _element[1] == content_id:
            _found_type = _element[0]
            return _found_type
    return None


def lookup_content_type_for_taggable_model_path(content_model_path):
    """Lookup content type for a GitRepository object."""
    _app_label = content_model_path.split(".", 1)[0]
    _model = content_model_path.split(".", 1)[1]

    return ContentType.objects.get(model=_model, app_label=_app_label)


def string_to_urlfield(url):
    """Turn string url into a URLField object."""
    url_validator = URLValidator()

    try:
        url_validator(url)
    except ValidationError:
        return models.URLField(default="https://example.com", blank=True)

    return models.URLField(default=url, blank=True, null=True)


def lookup_model_for_role_id(content_id):
    """Find a model path for a given ContentType ID."""
    _choices = RoleModelsQuery().get_choices()
    _found_type = None
    for _element in _choices:
        if _element[1] == content_id:
            _found_type = _element[0]
            return _found_type
    return None


def lookup_team_for_contact(team):
    """Find a Nautobot Team object by name and return the object."""
    try:
        _team = Team.objects.get(name=team)
        return _team
    except Team.DoesNotExist:
        return None


def lookup_contact_for_team(contact):
    """Find a Nautobot Contact object by name and return the object."""
    try:
        _contact = Contact.objects.get(name=contact)
        return _contact
    except Contact.DoesNotExist:
        return None


def get_scheduled_start_time(start_time):
    """Validate and return start_time in ISO 8601 format.

    Args:
        start_time (str): ISO 8601 formatted datetime string.

    Returns:
        str: ISO 8601 formatted datetime string with timezone info.
    """
    if not start_time:
        return ""
    try:
        # Check if timezone info is already present
        if "+" in start_time or "-" in start_time:
            # Validate the datetime format with existing timezone
            start_time = datetime.fromisoformat(start_time)
        else:
            # Validate the datetime format and convert to UTC
            start_time = datetime.fromisoformat(f"{start_time}+00:00")  # UTC, the Job stores time_zone info
        return start_time.isoformat()
    except ValueError:
        return None


def validate_software_version_status(status, version, logger):
    """Validate software version status against valid choices.

    Args:
        status (str): Status to validate
        version (str): Software version for logging
        logger: Logger instance for warnings

    Returns:
        str: Validated status or 'Active' if invalid
    """
    from nautobot.dcim.choices import SoftwareVersionStatusChoices  # pylint: disable=import-outside-toplevel

    # Get valid statuses preserving their original case
    valid_statuses = [choice[1] for choice in SoftwareVersionStatusChoices.CHOICES]

    # Check if the status matches any valid status (case-insensitive)
    matching_status = next((valid for valid in valid_statuses if valid.lower() == status.lower()), None)

    if not matching_status:
        logger.warning(
            f"Invalid status '{status}' for software version {version}. "
            f"Valid choices are: {valid_statuses}. "
            f"Using default status 'Active'."
        )
        return "Active"

    # Return the valid status with its original case
    return matching_status


def validate_software_image_status(status, image_name, logger):
    """Validate software image status against valid choices.

    Args:
        status (str): Status to validate
        image_name (str): Image name for logging
        logger: Logger instance for warnings

    Returns:
        str: Validated status (lowercase) or 'active' if invalid
    """
    from nautobot.dcim.choices import SoftwareImageFileStatusChoices  # pylint: disable=import-outside-toplevel

    valid_statuses = [choice[0].lower() for choice in SoftwareImageFileStatusChoices.CHOICES]
    if status.lower() not in valid_statuses:
        logger.warning(
            f"Invalid status '{status}' for software image {image_name}. "
            f"Valid choices are: {[choice[0] for choice in SoftwareImageFileStatusChoices.CHOICES]}. "
            f"Using default status 'active'."
        )
        return "active"
    return status.lower()


def validate_hashing_algorithm(algorithm, image_name, logger):
    """Validate hashing algorithm against valid choices.

    Args:
        algorithm (str): Algorithm to validate
        image_name (str): Image name for logging
        logger: Logger instance for warnings

    Returns:
        str: Validated algorithm or None if invalid
    """
    from nautobot.dcim.choices import (  # pylint: disable=import-outside-toplevel
        SoftwareImageFileHashingAlgorithmChoices,
    )

    if not algorithm:
        return None

    valid_algorithms = [choice[0].lower() for choice in SoftwareImageFileHashingAlgorithmChoices.CHOICES]
    if algorithm.lower() not in valid_algorithms:
        logger.warning(
            f"Invalid hashing algorithm '{algorithm}' for software image {image_name}. "
            f"Valid choices are: {[choice[0] for choice in SoftwareImageFileHashingAlgorithmChoices.CHOICES]}. "
            f"Setting to None."
        )
        return None
    return algorithm.lower()

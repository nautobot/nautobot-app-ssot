"""Signal handlers for OpenShift integration."""

from nautobot.apps import get_app_ui_menu_items


def register_signals(app):
    """Register signals for the OpenShift integration."""
    # Add OpenShift configuration to the SSoT menu
    menu_items = get_app_ui_menu_items(app, "plugins:nautobot_ssot:home")
    
    menu_items.append({
        "link": "plugins:nautobot_ssot:openshift:config_list",
        "link_text": "OpenShift Configurations",
        "buttons": [{
            "link": "plugins:nautobot_ssot:openshift:config_add",
            "link_text": "Add",
            "classes": "btn-sm btn-primary",
            "permissions": ["nautobot_ssot.add_ssotopenshiftconfig"],
        }],
        "permissions": ["nautobot_ssot.view_ssotopenshiftconfig"],
    })

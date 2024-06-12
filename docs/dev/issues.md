# Reference: Common Issues and Solutions

This pages describes common issues when implementing SSoT integrations and their respective solutions.

## Converting Types Between Database and Pydantic

Developers are able to override the default loading of basic parameters to control how that parameter is loaded from Nautobot.

This only works with basic parameters belonging to the model and does not override more complex parameters (foreign keys, custom fields, custom relationships, etc.).

To override a parameter, add a method with the name `load_param_{param_key}` to your adapter class inheriting from `NautobotAdapter`:

```python
from nautobot_ssot.contrib import NautobotAdapter

class YourSSoTNautobotAdapter(NautobotAdapter):
    ...    
    def load_param_time_zone(self, parameter_name, database_object):
        """Custom loader for `time_zone` parameter."""
        return str(getattr(database_object, parameter_name))
```

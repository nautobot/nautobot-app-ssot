# Debugging SSoT Jobs

When debugging SSoT jobs, it can be quite time-consuming to run the full job against the system fo record any time you make a change. As such, this page aims to describe steps to make this process easier.

## Debugging Model Methods

In order to debug the `create`, `update`, and `delete` methods on SSoT models, you can employ the following steps:

- Start a Python interpreter in the Nautobot environment with `nautobot-server shell_plus`
- Import your model into the interpreter (e.g. `from nautobot_ssot.integrations.aci.diffsync.models.nautobot import NautobotTenant`)
- Test the individual method you want to test directly:

```python
from nautobot_ssot.integrations.aci.diffsync.models.nautobot import NautobotTenant
# Note: You might need to instantiate your actual adapter and pass it in as the diffsync parameter, this may be the case
# if you are doing logging. `unittest.MagicMock` can help here as a substitute for e.g. an actual job class.
# If you want to test `create`
NautobotTenant.create(adapter=None, ids={"name": "Company A"}, attrs={"site_tag": "Something"})
tenant = NautobotTenant(name="Company A", site_tag="Something")
# If you want to test `update`
tenant.update(attrs={"site_tag": "Something else"})
# If you want to test `delete`
tenant.delete()
```

This way you can mock the SSoT framework itself calling these methods, and even insert `breakpoint`s in places where you need to [jump in with a debugger](https://docs.python.org/3/library/pdb.html).

## Debugging the Adapter(s) and the diff

If you want to debug the adapters themselves, you can use a similar approach:

```python
from nautobot_ssot.integrations.aci.diffsync.adapters.aci import AciAdapter
from nautobot_ssot.integrations.aci.diffsync.adapters.nautobot import NautobotAdapter
# For each adapter you will probably need some kind of API client or similar piece of software.
# This will be different depending on how your adapter is implemented. Here we just assume they exist already.
aci_adapter = AciAdapter(client=aci_client)
nautobot_adapter = NautobotAdapter(client=nautobot_client)

# This is what the SSoT job will call to load the data from your system of record
aci_adapter.load()
nautobot_adapter.load()
# At this point you can peek into the store of the adapters, the following example gives you all tenant objects loaded
# from ACI in a list.
tenants = aci_adapter.get_all("tenant")
# You can also look at the diff this way.
# Note: You will need to manually pass any flags that you are using here.
diff = aci_adapter.diff_to(nautobot_adapter)
# Now if you are satisifed you could even call the sync_to method to perform the actual data sync.
aci_adapter.sync_to(nautobot_adapter)
```

Note that again you can insert `breakpoint`s in your code do dig deeper with a debugger.
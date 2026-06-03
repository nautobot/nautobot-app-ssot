# Contrib Module

The `nautobot_ssot.contrib` module is a toolkit for building custom SSoT integrations syncing data from an external system into the local Nautobot instance. It provides base classes and reusable code to perform CRUD operations against the Nautobot ORM with some configurations and minimal additional code.

You declare your data models as thin, conventional descriptions of the corresponding Nautobot models, and `contrib` infers the rest — loading existing data, and creating, updating, and deleting records as a synchronization requires. This is the recommended starting point whenever you build a [custom integration](../integrations/index.md) of your own.

## Background

Every SSoT integration is built on [DiffSync](https://diffsync.readthedocs.io/en/latest/): you model the data on both sides as DiffSync models, load each side into an *adapter*, and let DiffSync calculate and reconcile the differences. The direction of that reconciliation is expressed as a Nautobot Job — a [`DataSource`](../../dev/jobs.md) (remote system into Nautobot) or a `DataTarget` (Nautobot into the remote system).

Writing the Nautobot side by hand means implementing `load`, `create`, `update`, and `delete` against the Nautobot ORM for every model — a large amount of repetitive boilerplate. The `contrib` module removes most of that work through two base classes:

- **`NautobotModel`** — a DiffSync model base class that provides `create`, `update`, and `delete` against the Nautobot ORM out of the box.
- **`NautobotAdapter`** — a DiffSync adapter base class that provides a generic `load` implementation, recursively traversing your models and their relationships.

Because this functionality is driven entirely by how your models are declared, the modeling conventions are the foundation everything else builds on.

## Where to start

The pages in this section build on each other in order:

1. **[Models](./models.md)** — defining `NautobotModel` subclasses, including the different field types covered in detail in the [modeling guide](../modeling.md).
2. **[Adapters](./adapters.md)** — assembling a `NautobotAdapter` from your models and customizing how data is loaded.

Once your models and adapters are in place, see [Developing Data Source and Data Target Jobs](../../dev/jobs.md) for wiring them into a runnable SSoT Job.

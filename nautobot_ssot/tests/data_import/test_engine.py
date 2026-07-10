"""End-to-end engine tests: run_plan over CSV data creating real objects."""

from django.test import TestCase
from nautobot.dcim.models import Location, LocationType, Manufacturer

from nautobot_ssot.integrations.data_import.engine.runner import run_plan, validate_document
from nautobot_ssot.integrations.data_import.models import ImportPlan

SITES_CSV = "site_name,kind,vendor\nDC1,Data Center,Cisco\nDC2,Data Center,Arista\nBR-1,Branch,Cisco\n"


def _sites_document():
    return {
        "version": 2,
        "sources": [{"id": "sites", "type": "csv"}],
        "tables": [{"id": "sites", "from": "sites"}],
        "outputs": [
            {
                "table": "sites",
                "to": "dcim.location",
                "identifiers": {"name": {"column": "site_name"}},
                "fields": {
                    "location_type": {
                        "column": "kind",
                        "fk": {"on_missing": "create", "lookup_field": "name"},
                    },
                    "status": {"fk": {"on_missing": "static", "lookup_field": "name", "static_value": "Active"}},
                },
            }
        ],
        "defaults": {"on_record_error": "continue"},
    }


class RunPlanTests(TestCase):
    """run_plan end to end with a CSV source."""

    def _make_plan(self):
        return ImportPlan.objects.create(
            name="sites-from-csv",
            document=_sites_document(),
            csv_data={"sites": SITES_CSV},
        )

    def test_validate_document_reports_problems(self):
        problems = validate_document({})
        self.assertTrue(problems)
        problems = validate_document(_sites_document())
        self.assertEqual(problems, [])

    def test_dry_run_writes_nothing(self):
        plan = self._make_plan()
        before_locations = Location.objects.count()
        before_types = LocationType.objects.count()
        summary = run_plan(plan, dry_run=True)
        self.assertEqual(summary["totals"]["created"], 3)
        self.assertEqual(Location.objects.count(), before_locations)
        self.assertEqual(LocationType.objects.count(), before_types)

    def test_live_run_creates_and_is_idempotent(self):
        plan = self._make_plan()
        summary = run_plan(plan, dry_run=False)
        self.assertEqual(summary["totals"]["created"], 3, summary)
        self.assertTrue(Location.objects.filter(name="DC1").exists())
        # FK create strategy auto-created the LocationTypes.
        self.assertTrue(LocationType.objects.filter(name="Data Center").exists())
        self.assertTrue(LocationType.objects.filter(name="Branch").exists())
        # Static status applied.
        self.assertEqual(Location.objects.get(name="DC1").status.name, "Active")

        second = run_plan(plan, dry_run=False)
        self.assertEqual(second["totals"]["created"], 0, second)
        self.assertEqual(second["totals"]["unchanged"], 3, second)

    def test_skip_record_on_missing_fk(self):
        document = _sites_document()
        document["outputs"][0]["fields"]["location_type"]["fk"]["on_missing"] = "skip_record"
        plan = ImportPlan.objects.create(name="sites-skip", document=document, csv_data={"sites": SITES_CSV})
        summary = run_plan(plan, dry_run=False)
        # No LocationType named "Data Center"/"Branch" exists → all rows skipped.
        self.assertEqual(summary["totals"]["created"], 0, summary)
        self.assertEqual(summary["totals"]["skipped"], 3, summary)

    def test_value_map_applied(self):
        document = _sites_document()
        document["outputs"][0]["fields"]["location_type"]["value_map"] = {
            "Data Center": "Datacenter",
            "Branch": "Branch Office",
        }
        plan = ImportPlan.objects.create(name="sites-vm", document=document, csv_data={"sites": SITES_CSV})
        run_plan(plan, dry_run=False)
        self.assertTrue(LocationType.objects.filter(name="Datacenter").exists())
        self.assertTrue(LocationType.objects.filter(name="Branch Office").exists())


class ResolverCreateDefaultsTests(TestCase):
    """create_defaults with __ traversal (parent cascade)."""

    def test_column_ref_and_parent_traversal(self):
        from django.contrib.contenttypes.models import ContentType  # pylint: disable=import-outside-toplevel
        from nautobot.dcim.models import DeviceType  # pylint: disable=import-outside-toplevel

        from nautobot_ssot.integrations.data_import.engine.resolver import (  # pylint: disable=import-outside-toplevel
            FKResolver,
        )

        device_ct = ContentType.objects.get(app_label="dcim", model="device")
        device_type_field = device_ct.model_class()._meta.get_field("device_type")

        resolver = FKResolver(dry_run=False)
        row = {"model": "C9300-48P", "vendor": "Cisco"}
        fk_cfg = {
            "on_missing": "create",
            "lookup_field": "model",
            "create_defaults": {"manufacturer__name": {"column": "vendor"}},
        }
        instance = resolver.resolve(device_type_field, fk_cfg, row["model"], row)
        self.assertIsInstance(instance, DeviceType)
        self.assertEqual(instance.model, "C9300-48P")
        self.assertEqual(instance.manufacturer.name, "Cisco")
        self.assertTrue(Manufacturer.objects.filter(name="Cisco").exists())


class ResolverLookupTypeTests(TestCase):
    """Field-type-aware lookups: no iexact on non-text fields, _cf_ lookups."""

    def test_lookup_on_binary_ip_field(self):
        """Device.primary_ip4 resolves by IPAddress.host (VarbinaryIPField) — iexact unsupported there."""
        from nautobot.dcim.models import Device  # pylint: disable=import-outside-toplevel
        from nautobot.extras.models import Status  # pylint: disable=import-outside-toplevel
        from nautobot.ipam.models import IPAddress, Namespace, Prefix  # pylint: disable=import-outside-toplevel

        from nautobot_ssot.integrations.data_import.engine.resolver import (  # pylint: disable=import-outside-toplevel
            SKIP_RECORD,
            FKResolver,
        )

        namespace = Namespace.objects.get(name="Global")
        active = Status.objects.get(name="Active")
        Prefix.objects.create(prefix="10.0.0.0/8", namespace=namespace, status=active)
        ip_address = IPAddress.objects.create(address="10.0.255.252/32", namespace=namespace, status=active)

        primary_ip4_field = Device._meta.get_field("primary_ip4")
        resolver = FKResolver(dry_run=False)
        fk_cfg = {"on_missing": "skip_record", "lookup_field": "host"}
        resolved = resolver.resolve(primary_ip4_field, fk_cfg, "10.0.255.252", {})
        self.assertEqual(resolved, ip_address)
        # A miss must return SKIP_RECORD, not raise "Lookup not supported".
        resolved_miss = resolver.resolve(primary_ip4_field, fk_cfg, "10.9.9.9", {})
        self.assertIs(resolved_miss, SKIP_RECORD)

    def test_lookup_by_custom_field(self):
        """Interface.device resolves via a _cf_ lookup field on Device."""
        from django.contrib.contenttypes.models import ContentType  # pylint: disable=import-outside-toplevel
        from nautobot.dcim.models import (  # pylint: disable=import-outside-toplevel
            Device,
            DeviceType,
            Interface,
            Location,
            LocationType,
        )
        from nautobot.extras.choices import CustomFieldTypeChoices  # pylint: disable=import-outside-toplevel
        from nautobot.extras.models import CustomField, Role, Status  # pylint: disable=import-outside-toplevel

        from nautobot_ssot.integrations.data_import.engine.resolver import (  # pylint: disable=import-outside-toplevel
            SKIP_RECORD,
            FKResolver,
        )

        device_ct = ContentType.objects.get_for_model(Device)
        custom_field = CustomField.objects.create(
            key="di_test_external_id", type=CustomFieldTypeChoices.TYPE_TEXT, label="LibreNMS ID"
        )
        custom_field.content_types.add(device_ct)

        active = Status.objects.get(name="Active")
        location_type = LocationType.objects.create(name="Site")
        location_type.content_types.add(device_ct)
        location = Location.objects.create(name="Test DC", location_type=location_type, status=active)
        manufacturer = Manufacturer.objects.create(name="TestVendor")
        device_type = DeviceType.objects.create(model="TestModel", manufacturer=manufacturer)
        role = Role.objects.create(name="TestRole")
        role.content_types.add(device_ct)
        device = Device.objects.create(
            name="rtr-1", device_type=device_type, role=role, status=active, location=location
        )
        device.custom_field_data["di_test_external_id"] = "16"
        device.save()

        interface_device_field = Interface._meta.get_field("device")
        resolver = FKResolver(dry_run=False)
        fk_cfg = {"on_missing": "skip_record", "lookup_field": "_cf_di_test_external_id"}
        resolved = resolver.resolve(interface_device_field, fk_cfg, "16", {})
        self.assertEqual(resolved, device)
        # Numeric raw value (int from JSON) also matches the stored string.
        resolver2 = FKResolver(dry_run=False)
        resolved_int = resolver2.resolve(interface_device_field, fk_cfg, 16, {})
        self.assertEqual(resolved_int, device)
        resolved_miss = resolver.resolve(interface_device_field, fk_cfg, "999", {})
        self.assertIs(resolved_miss, SKIP_RECORD)


class IPAddressAutoCreateTests(TestCase):
    """IPAddress FK auto-create: mask defaulting + parent Prefix provisioning."""

    def test_create_ip_with_auto_parent_prefix(self):
        from nautobot.dcim.models import Device  # pylint: disable=import-outside-toplevel
        from nautobot.ipam.models import IPAddress, Prefix  # pylint: disable=import-outside-toplevel

        from nautobot_ssot.integrations.data_import.engine.resolver import (  # pylint: disable=import-outside-toplevel
            FKResolver,
        )

        primary_ip4_field = Device._meta.get_field("primary_ip4")
        resolver = FKResolver(dry_run=False)
        fk_cfg = {"on_missing": "create", "lookup_field": "host"}
        instance = resolver.resolve(primary_ip4_field, fk_cfg, "10.9.8.7", {})
        self.assertIsInstance(instance, IPAddress)
        self.assertEqual(str(instance.host), "10.9.8.7")
        self.assertEqual(instance.mask_length, 32)
        # A covering /24 container was provisioned automatically.
        self.assertTrue(Prefix.objects.filter(network="10.9.8.0", prefix_length=24).exists())
        # Second resolve for the same value hits the cache/lookup, no duplicate.
        again = resolver.resolve(primary_ip4_field, fk_cfg, "10.9.8.7", {})
        self.assertEqual(again.pk, instance.pk)
        self.assertEqual(IPAddress.objects.filter(host="10.9.8.7").count(), 1)

    def test_existing_parent_prefix_is_reused(self):
        from nautobot.dcim.models import Device  # pylint: disable=import-outside-toplevel
        from nautobot.extras.models import Status  # pylint: disable=import-outside-toplevel
        from nautobot.ipam.models import Namespace, Prefix  # pylint: disable=import-outside-toplevel

        from nautobot_ssot.integrations.data_import.engine.resolver import (  # pylint: disable=import-outside-toplevel
            FKResolver,
        )

        namespace = Namespace.objects.get(name="Global")
        active = Status.objects.get(name="Active")
        Prefix.objects.create(prefix="10.20.0.0/16", namespace=namespace, status=active)

        primary_ip4_field = Device._meta.get_field("primary_ip4")
        resolver = FKResolver(dry_run=False)
        instance = resolver.resolve(
            primary_ip4_field, {"on_missing": "create", "lookup_field": "host"}, "10.20.30.40", {}
        )
        self.assertEqual(str(instance.host), "10.20.30.40")
        # No extra /24 container created — the /16 already contains the IP.
        self.assertFalse(Prefix.objects.filter(network="10.20.30.0", prefix_length=24).exists())

    def test_dry_run_projects_without_writing(self):
        from nautobot.dcim.models import Device  # pylint: disable=import-outside-toplevel
        from nautobot.ipam.models import IPAddress  # pylint: disable=import-outside-toplevel

        from nautobot_ssot.integrations.data_import.engine.resolver import (  # pylint: disable=import-outside-toplevel
            FKResolver,
        )

        primary_ip4_field = Device._meta.get_field("primary_ip4")
        resolver = FKResolver(dry_run=True)
        marker = resolver.resolve(
            primary_ip4_field, {"on_missing": "create", "lookup_field": "host"}, "10.99.99.99", {}
        )
        self.assertIsInstance(marker, dict)
        self.assertIn("__dry_created__", marker)
        self.assertFalse(IPAddress.objects.filter(host="10.99.99.99").exists())


class PrimaryIPAndRequiredFieldTests(TestCase):
    """Deferred primary IP assignment + required-field skip guard."""

    DEVICES_CSV = (
        "hostname,ip,model,vendor,site,kind\n"
        "rtr-a,10.77.1.1,RB5009,MikroTik,DC-X,Data Center\n"
        "srv-nohw,10.77.1.2,,,DC-X,Data Center\n"  # no hardware → device_type unresolvable
    )

    def _make_plan(self):
        document = {
            "version": 2,
            "sources": [{"id": "devices", "type": "csv"}],
            "tables": [{"id": "devices", "from": "devices"}],
            "outputs": [
                {
                    "table": "devices",
                    "to": "dcim.device",
                    "identifiers": {"name": {"column": "hostname"}},
                    "fields": {
                        "status": {"fk": {"on_missing": "static", "lookup_field": "name", "static_value": "Active"}},
                        "role": {"fixed": "network", "fk": {"on_missing": "create", "lookup_field": "name"}},
                        "device_type": {
                            "column": "model",
                            "fk": {
                                "on_missing": "create",
                                "lookup_field": "model",
                                "create_defaults": {"manufacturer__name": {"column": "vendor"}},
                            },
                        },
                        "location": {
                            "column": "site",
                            "fk": {
                                "on_missing": "create",
                                "lookup_field": "name",
                                "create_defaults": {"location_type__name": {"column": "kind"}},
                            },
                        },
                        "primary_ip4": {"column": "ip", "fk": {"on_missing": "create", "lookup_field": "host"}},
                    },
                }
            ],
            "defaults": {"on_record_error": "continue"},
        }
        return ImportPlan.objects.create(
            name="devices-with-primary-ip", document=document, csv_data={"devices": self.DEVICES_CSV}
        )

    def test_primary_ip_assigned_via_mgmt_interface(self):
        from nautobot.dcim.models import Device, Interface  # pylint: disable=import-outside-toplevel
        from nautobot.ipam.models import IPAddressToInterface  # pylint: disable=import-outside-toplevel

        plan = self._make_plan()
        summary = run_plan(plan, dry_run=False)
        by_target = {s["target"]: s for s in summary["outputs"]}
        self.assertEqual(by_target["dcim.device"]["created"], 1, summary)
        # The no-hardware record skips with a clear reason, not a validation error.
        self.assertEqual(by_target["dcim.device"]["skipped"], 1, summary)
        self.assertEqual(by_target["dcim.device"]["errors"], [], summary)
        skip = next(r for r in by_target["dcim.device"]["records"] if r["action"] == "skip")
        self.assertIn("device_type", skip["reason"])

        device = Device.objects.get(name="rtr-a")
        self.assertIsNotNone(device.primary_ip4)
        self.assertEqual(str(device.primary_ip4.host), "10.77.1.1")
        mgmt = Interface.objects.get(device=device, name="mgmt")
        self.assertTrue(IPAddressToInterface.objects.filter(ip_address=device.primary_ip4, interface=mgmt).exists())

    def test_second_run_is_unchanged(self):
        plan = self._make_plan()
        run_plan(plan, dry_run=False)
        second = run_plan(plan, dry_run=False)
        by_target = {s["target"]: s for s in second["outputs"]}
        self.assertEqual(by_target["dcim.device"]["created"], 0, second)
        self.assertEqual(by_target["dcim.device"]["updated"], 0, second)
        self.assertEqual(by_target["dcim.device"]["unchanged"], 1, second)

    def test_default_fills_missing_required_fk(self):
        from nautobot.dcim.models import Device  # pylint: disable=import-outside-toplevel

        plan = self._make_plan()
        plan.document["outputs"][0]["fields"]["device_type"]["default"] = "Generic Server"
        plan.save()
        summary = run_plan(plan, dry_run=False)
        by_target = {s["target"]: s for s in summary["outputs"]}
        self.assertEqual(by_target["dcim.device"]["created"], 2, summary)
        self.assertEqual(Device.objects.get(name="srv-nohw").device_type.model, "Generic Server")


class CrossOutputDryRunTests(TestCase):
    """Dry-run FK lookups resolve against objects projected by earlier outputs."""

    CSV_SITES = "site_name,kind\nXDC1,XSite\nXDC2,XSite\n"
    CSV_RACKS = "rack_name,site\nRK-1,XDC1\nRK-2,XDC2\nRK-orphan,NOPE\n"

    def _make_plan(self):
        document = {
            "version": 2,
            "sources": [{"id": "sites", "type": "csv"}, {"id": "racks", "type": "csv"}],
            "tables": [{"id": "sites", "from": "sites"}, {"id": "racks", "from": "racks"}],
            "outputs": [
                # Declared racks-first on purpose: topo sort must run locations first.
                {
                    "table": "racks",
                    "to": "dcim.rack",
                    "identifiers": {"name": {"column": "rack_name"}},
                    "fields": {
                        "location": {
                            "column": "site",
                            "fk": {"on_missing": "skip_record", "lookup_field": "name"},
                        },
                        "status": {"fk": {"on_missing": "static", "lookup_field": "name", "static_value": "Active"}},
                    },
                },
                {
                    "table": "sites",
                    "to": "dcim.location",
                    "identifiers": {"name": {"column": "site_name"}},
                    "fields": {
                        "location_type": {"column": "kind", "fk": {"on_missing": "create", "lookup_field": "name"}},
                        "status": {"fk": {"on_missing": "static", "lookup_field": "name", "static_value": "Active"}},
                    },
                },
            ],
            "defaults": {"on_record_error": "continue"},
        }
        return ImportPlan.objects.create(
            name="cross-output",
            document=document,
            csv_data={"sites": self.CSV_SITES, "racks": self.CSV_RACKS},
        )

    def test_dry_run_resolves_projected_locations(self):
        plan = self._make_plan()
        summary = run_plan(plan, dry_run=True)
        by_target = {s["target"]: s for s in summary["outputs"]}
        # Locations project 2 creates; racks resolve against them.
        self.assertEqual(by_target["dcim.location"]["created"], 2, summary)
        self.assertEqual(by_target["dcim.rack"]["created"], 2, summary)
        # The orphan rack still skips (its site exists nowhere, projected or real).
        self.assertEqual(by_target["dcim.rack"]["skipped"], 1, summary)
        # Marker display is human-readable, not a raw dict.
        rack_creates = [r for r in by_target["dcim.rack"]["records"] if r["action"] == "create"]
        self.assertIn("created earlier in this import", rack_creates[0]["values"]["location"])
        self.assertNotIn("__pending__", rack_creates[0]["values"]["location"])

    def test_live_run_orders_and_creates(self):
        from nautobot.dcim.models import Rack  # pylint: disable=import-outside-toplevel

        plan = self._make_plan()
        summary = run_plan(plan, dry_run=False)
        by_target = {s["target"]: s for s in summary["outputs"]}
        self.assertEqual(by_target["dcim.location"]["created"], 2, summary)
        self.assertEqual(by_target["dcim.rack"]["created"], 2, summary)
        self.assertTrue(Rack.objects.filter(name="RK-1", location__name="XDC1").exists())

    def test_no_duplicate_auto_created_entries(self):
        plan = self._make_plan()
        summary = run_plan(plan, dry_run=True)
        entries = summary["auto_created_related"]
        self.assertEqual(len(entries), len(set(entries)), entries)


class ContentTypeScopeTests(TestCase):
    """Found Status/Role objects must be enabled for the target model."""

    def _scoped_status(self, name):
        """A Status enabled only for VRFs (like LibreNMS's 'Down')."""
        from django.contrib.contenttypes.models import ContentType  # pylint: disable=import-outside-toplevel
        from nautobot.extras.models import Status  # pylint: disable=import-outside-toplevel

        status = Status.objects.create(name=name)
        status.content_types.set([ContentType.objects.get(app_label="ipam", model="vrf")])
        return status

    def test_create_strategy_extends_content_types(self):
        from django.contrib.contenttypes.models import ContentType  # pylint: disable=import-outside-toplevel
        from nautobot.dcim.models import Interface  # pylint: disable=import-outside-toplevel

        from nautobot_ssot.integrations.data_import.engine.resolver import (  # pylint: disable=import-outside-toplevel
            FKResolver,
        )

        status = self._scoped_status("TestDown")
        interface_status_field = Interface._meta.get_field("status")
        resolver = FKResolver(dry_run=False)
        resolved = resolver.resolve(
            interface_status_field, {"on_missing": "create", "lookup_field": "name"}, "testdown", {}
        )
        self.assertEqual(resolved.pk, status.pk)
        interface_ct = ContentType.objects.get(app_label="dcim", model="interface")
        self.assertTrue(status.content_types.filter(pk=interface_ct.pk).exists())

    def test_lookup_strategy_treats_out_of_scope_as_miss(self):
        from nautobot.dcim.models import Interface  # pylint: disable=import-outside-toplevel

        from nautobot_ssot.integrations.data_import.engine.resolver import (  # pylint: disable=import-outside-toplevel
            SKIP_RECORD,
            FKResolver,
        )

        status = self._scoped_status("TestDown2")
        interface_status_field = Interface._meta.get_field("status")
        resolver = FKResolver(dry_run=False)
        resolved = resolver.resolve(
            interface_status_field, {"on_missing": "skip_record", "lookup_field": "name"}, "testdown2", {}
        )
        self.assertIs(resolved, SKIP_RECORD)
        # And the object was NOT mutated.
        self.assertEqual(status.content_types.count(), 1)


class FieldPreValidationTests(TestCase):
    """Django-field pre-validation: bad choices skip, overflow drops optional fields."""

    def _base_plan(self, csv_text, fields_extra):
        fields = {
            "location_type": {"column": "kind", "fk": {"on_missing": "create", "lookup_field": "name"}},
            "status": {"fk": {"on_missing": "static", "lookup_field": "name", "static_value": "Active"}},
        }
        fields.update(fields_extra)
        document = {
            "version": 2,
            "sources": [{"id": "rows", "type": "csv"}],
            "tables": [{"id": "rows", "from": "rows"}],
            "outputs": [
                {
                    "table": "rows",
                    "to": "dcim.location",
                    "identifiers": {"name": {"column": "site_name"}},
                    "fields": fields,
                }
            ],
            "defaults": {"on_record_error": "continue"},
        }
        return ImportPlan.objects.create(name="prevalidation", document=document, csv_data={"rows": csv_text})

    def test_out_of_range_optional_field_dropped_not_fatal(self):
        # Location.latitude has range validation; a bad value should drop the
        # field but still import the record (latitude is optional).
        plan = self._base_plan(
            "site_name,kind,lat\nPV-1,PV Site,999999\n",
            {"latitude": {"column": "lat"}},
        )
        summary = run_plan(plan, dry_run=False)
        by_target = {s["target"]: s for s in summary["outputs"]}
        self.assertEqual(by_target["dcim.location"]["created"], 1, summary)
        self.assertTrue(Location.objects.filter(name="PV-1", latitude__isnull=True).exists())
        self.assertTrue(any("latitude" in e for e in by_target["dcim.location"]["errors"]), summary)

    def test_type_cast_via_field_clean(self):
        # String numbers from CSV are cast by field.clean before save.
        plan = self._base_plan(
            "site_name,kind,lat\nPV-2,PV Site,45.5\n",
            {"latitude": {"column": "lat"}},
        )
        summary = run_plan(plan, dry_run=False)
        self.assertEqual(summary["totals"]["created"], 1, summary)
        self.assertAlmostEqual(float(Location.objects.get(name="PV-2").latitude), 45.5)


class CompositeIdentifierTests(TestCase):
    """Interfaces identified by (name, device) — same name on two devices must not collide."""

    DEVICES_CSV = (
        "hostname,ip,model,vendor,site,kind\n"
        "sw-a,10.88.1.1,CRS326,MikroTik,DC-Y,Data Center\n"
        "sw-b,10.88.1.2,CRS326,MikroTik,DC-Y,Data Center\n"
    )
    # lo0 exists on BOTH devices; ether1 only on sw-a.
    PORTS_CSV = "device,ifname,iftype\nsw-a,lo0,virtual\nsw-b,lo0,virtual\nsw-a,ether1,other\n"

    def _make_plan(self):
        document = {
            "version": 2,
            "sources": [{"id": "devices", "type": "csv"}, {"id": "ports", "type": "csv"}],
            "tables": [{"id": "devices", "from": "devices"}, {"id": "ports", "from": "ports"}],
            "outputs": [
                {
                    "table": "devices",
                    "to": "dcim.device",
                    "identifiers": {"name": {"column": "hostname"}},
                    "fields": {
                        "status": {"fk": {"on_missing": "static", "lookup_field": "name", "static_value": "Active"}},
                        "role": {"fixed": "network", "fk": {"on_missing": "create", "lookup_field": "name"}},
                        "device_type": {
                            "column": "model",
                            "fk": {
                                "on_missing": "create",
                                "lookup_field": "model",
                                "create_defaults": {"manufacturer__name": {"column": "vendor"}},
                            },
                        },
                        "location": {
                            "column": "site",
                            "fk": {
                                "on_missing": "create",
                                "lookup_field": "name",
                                "create_defaults": {"location_type__name": {"column": "kind"}},
                            },
                        },
                    },
                },
                {
                    "table": "ports",
                    "to": "dcim.interface",
                    "identifiers": {
                        "name": {"column": "ifname"},
                        "device": {"column": "device", "fk": {"on_missing": "skip_record", "lookup_field": "name"}},
                    },
                    "fields": {
                        "status": {"fk": {"on_missing": "static", "lookup_field": "name", "static_value": "Active"}},
                        "type": {"column": "iftype"},
                    },
                },
            ],
            "defaults": {"on_record_error": "continue"},
        }
        return ImportPlan.objects.create(
            name="composite-idents",
            document=document,
            csv_data={"devices": self.DEVICES_CSV, "ports": self.PORTS_CSV},
        )

    def test_same_interface_name_on_two_devices(self):
        from nautobot.dcim.models import Interface  # pylint: disable=import-outside-toplevel

        plan = self._make_plan()
        summary = run_plan(plan, dry_run=False)
        by_target = {s["target"]: s for s in summary["outputs"]}
        self.assertEqual(by_target["dcim.interface"]["created"], 3, summary)
        self.assertEqual(by_target["dcim.interface"]["errors"], [], summary)
        self.assertEqual(Interface.objects.filter(name="lo0").count(), 2)
        self.assertTrue(Interface.objects.filter(name="lo0", device__name="sw-a").exists())
        self.assertTrue(Interface.objects.filter(name="lo0", device__name="sw-b").exists())

        second = run_plan(plan, dry_run=False)
        by_target2 = {s["target"]: s for s in second["outputs"]}
        self.assertEqual(by_target2["dcim.interface"]["created"], 0, second)
        self.assertEqual(by_target2["dcim.interface"]["unchanged"], 3, second)


class ValidationRecoveryTests(TestCase):
    """Cross-field model validation drops offending optional fields and retries."""

    def test_speed_dropped_for_virtual_interface(self):
        from nautobot.dcim.models import Interface  # pylint: disable=import-outside-toplevel

        document = {
            "version": 2,
            "sources": [{"id": "devices", "type": "csv"}, {"id": "ports", "type": "csv"}],
            "tables": [{"id": "devices", "from": "devices"}, {"id": "ports", "from": "ports"}],
            "outputs": [
                {
                    "table": "devices",
                    "to": "dcim.device",
                    "identifiers": {"name": {"column": "hostname"}},
                    "fields": {
                        "status": {"fk": {"on_missing": "static", "lookup_field": "name", "static_value": "Active"}},
                        "role": {"fixed": "network", "fk": {"on_missing": "create", "lookup_field": "name"}},
                        "device_type": {
                            "column": "model",
                            "fk": {
                                "on_missing": "create",
                                "lookup_field": "model",
                                "create_defaults": {"manufacturer__name": {"column": "vendor"}},
                            },
                        },
                        "location": {
                            "column": "site",
                            "fk": {
                                "on_missing": "create",
                                "lookup_field": "name",
                                "create_defaults": {"location_type__name": {"column": "kind"}},
                            },
                        },
                    },
                },
                {
                    "table": "ports",
                    "to": "dcim.interface",
                    "identifiers": {
                        "name": {"column": "ifname"},
                        "device": {"column": "device", "fk": {"on_missing": "skip_record", "lookup_field": "name"}},
                    },
                    "fields": {
                        "status": {"fk": {"on_missing": "static", "lookup_field": "name", "static_value": "Active"}},
                        "type": {"column": "iftype"},
                        "speed": {"column": "speed", "type_cast": "int"},
                    },
                },
            ],
            "defaults": {"on_record_error": "continue"},
        }
        plan = ImportPlan.objects.create(
            name="validation-recovery",
            document=document,
            csv_data={
                "devices": "hostname,ip,model,vendor,site,kind\nsw-v,10.89.1.1,CRS326,MikroTik,DC-Z,Data Center\n",
                # virtual interface with a speed → model validation rejects speed
                "ports": "device,ifname,iftype,speed\nsw-v,vlan10,virtual,1000000\nsw-v,ether1,other,1000000\n",
            },
        )
        summary = run_plan(plan, dry_run=False)
        by_target = {s["target"]: s for s in summary["outputs"]}
        # Both interfaces imported; the virtual one lost its speed with a note.
        self.assertEqual(by_target["dcim.interface"]["created"], 2, summary)
        vlan10 = Interface.objects.get(name="vlan10", device__name="sw-v")
        self.assertIsNone(vlan10.speed)
        self.assertTrue(any("imported without speed" in e for e in by_target["dcim.interface"]["errors"]), summary)


class ErrorDedupTests(TestCase):
    """Repeated identical root causes collapse into one summary line."""

    def test_dedupe(self):
        from nautobot_ssot.integrations.data_import.engine.loader import (
            _dedupe_errors,  # pylint: disable=import-outside-toplevel
        )

        errors = [f"row {i}: Lookup not supported on postgresql." for i in range(1, 51)]
        errors.append("rtr-1: something else entirely")
        deduped = _dedupe_errors(errors)
        self.assertEqual(len(deduped), 2)
        self.assertIn("(×50 rows)", deduped[0])

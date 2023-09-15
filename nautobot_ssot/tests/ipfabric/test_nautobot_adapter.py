# """Unit tests for the IPFabric DiffSync adapter class."""

# import uuid

# from django.contrib.contenttypes.models import ContentType
# from django.test import TestCase
# from nautobot.dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
# from nautobot.extras.models import Job, JobResult, Status
# from nautobot.ipam.models import VLAN

# from nautobot_ssot_ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
# from nautobot_ssot_ipfabric.jobs import IpFabricDataSource


# class IPFabricDiffSyncTestCase(TestCase):
#     """Test the NautobotDiffSync adapter class."""

#     def setUp(self):
#         """Create Nautobot objects to load and test with."""
#         status_active = Status.objects.get(slug="active")

#         site_1 = Site.objects.create(name="Site 1", slug="site-1", status=status_active)
#         site_2 = Site.objects.create(name="Site 2", slug="site-2", status=status_active)

#         manufacturer = Manufacturer.objects.create(name="Cisco", slug="cisco")
#         device_type = DeviceType.objects.create(manufacturer=manufacturer, model="CSR 1000v", slug="csr1000v")
#         device_role = DeviceRole.objects.create(name="Router", slug="router")

#         Device.objects.create(
#             name="csr1", device_type=device_type, device_role=device_role, site=site_1, status=status_active
#         )
#         Device.objects.create(
#             name="csr2", device_type=device_type, device_role=device_role, site=site_2, status=status_active
#         )

#         VLAN.objects.create(name="VLAN101", vid=101, status=status_active, site=site_1)

#     def test_data_loading(self):
#         """Test the load() function."""

#         job = IpFabricDataSource()
#         job.job_result = JobResult.objects.create(
#             name=job.class_path, obj_type=ContentType.objects.get_for_model(Job), user=None, job_id=uuid.uuid4()
#         )

#         nautobot = NautobotDiffSync(
#             job=job,
#             sync=None,
#             safe_delete_mode=True,
#             sync_ipfabric_tagged_only=True,
#         )
#         nautobot.load()

#         self.assertEqual(
#             set(["Site 1", "Site 2"]),
#             {site.get_unique_id() for site in nautobot.get_all("location")},
#         )
#         self.assertEqual(
#             set(["csr1", "csr2"]),
#             {dev.get_unique_id() for dev in nautobot.get_all("device")},
#         )

#         # Assert each site has a device tied to it.
#         for device in nautobot.get_all("device"):
#             self.assertTrue(hasattr(device, "location_name"), f"{device} is missing location_name")
#             self.assertTrue(hasattr(device, "model"), f"{device} is missing model")
#             self.assertTrue(hasattr(device, "name"), f"{device} is missing name")
#             # These attributes don't exist on our Device DiffSyncModel yet but we may want them there in the future
#             # self.assertTrue(hasattr(device, "platform"))
#             # self.assertTrue(hasattr(device, "role"))
#             # self.assertTrue(hasattr(device, "status"))
#             self.assertTrue(hasattr(device, "serial_number"), f"{device} is missing serial_number")

#         # Assert each vlan has the necessary attributes
#         for vlan in nautobot.get_all("vlan"):
#             self.assertTrue(hasattr(vlan, "name"))
#             self.assertTrue(hasattr(vlan, "vid"))
#             self.assertTrue(hasattr(vlan, "status"))
#             self.assertTrue(hasattr(vlan, "site"))

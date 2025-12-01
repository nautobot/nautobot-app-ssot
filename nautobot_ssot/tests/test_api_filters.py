from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from nautobot.core.testing import APIViewTestCases
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.models import Role, Status

from nautobot_ssot.models import Sync, SyncRecord


class SyncRecordFilterTestCase(APIViewTestCases.APIViewTestCase):
    model = SyncRecord
    brief_fields = [
        "id",
        "url",
        "sync",
        "source_adapter",
        "target_adapter",
        "obj_type",
        "obj_name",
        "action",
        "status",
        "message",
        "synced_object_id",
        "synced_object_type",
    ]

    @classmethod
    def setUpTestData(cls):
        location_type = LocationType.objects.create(name="Test Location Type")
        location = Location.objects.create(
            name="Test Location", location_type=location_type, status=Status.objects.get(name="Pending")
        )
        manufacturer = Manufacturer.objects.create(name="Test Manufacturer")
        device_type = DeviceType.objects.create(model="Test Device Type", manufacturer=manufacturer)
        role = Role.objects.create(name="Test Role")
        device = Device.objects.create(
            name="Test Device",
            device_type=device_type,
            role=role,
            location=location,
            status=Status.objects.get(name="Pending"),
        )

        sync = Sync.objects.create(source="Test Source", target="Test Target", diff={})

        cls.sync_record = SyncRecord.objects.create(
            sync=sync,
            source_adapter="Test Source",
            target_adapter="Test Target",
            obj_type="Device",
            obj_name="Test Device",
            action="NO_CHANGE",
            status=Status.objects.get(name="Pending"),
            synced_object=device,
        )

        SyncRecord.objects.create(
            sync=sync,
            source_adapter="Test Source",
            target_adapter="Test Target",
            obj_type="Device",
            obj_name="Test Device 2",
            action="NO_CHANGE",
            status=Status.objects.get(name="Pending"),
            synced_object=device,
        )

        SyncRecord.objects.create(
            sync=sync,
            source_adapter="Test Source",
            target_adapter="Test Target",
            obj_type="Device",
            obj_name="Test Device 3",
            action="NO_CHANGE",
            status=Status.objects.get(name="Pending"),
            synced_object=device,
        )

        cls.device2 = Device.objects.create(
            name="Test Device 2",
            device_type=device_type,
            role=role,
            location=location,
            status=Status.objects.get(name="Pending"),
        )
        cls.sync_record2 = SyncRecord.objects.create(
            sync=sync,
            source_adapter="Test Source",
            target_adapter="Test Target",
            obj_type="Device",
            obj_name="Test Device 4",
            action="NO_CHANGE",
            status=Status.objects.get(name="Pending"),
            synced_object=cls.device2,
        )

    def test_filter_by_synced_object(self):
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        url = reverse("plugins-api:nautobot_ssot-api:syncrecord-list")

        # Test filtering by synced_object_id for device 1
        response = self.client.get(f"{url}?synced_object_id={self.sync_record.synced_object_id}")
        if response.status_code != 200:
            print(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)

        # Test filtering by synced_object_id for device 2
        response = self.client.get(f"{url}?synced_object_id={self.device2.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(str(response.data["results"][0]["id"]), str(self.sync_record2.id))

        # Test filtering by synced_object_type
        content_type_id = ContentType.objects.get_for_model(Device).id
        response = self.client.get(f"{url}?synced_object_type={content_type_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 4)  # All 4 records are for Devices

        # Test filtering by both
        response = self.client.get(
            f"{url}?synced_object_id={self.sync_record.synced_object_id}&synced_object_type={content_type_id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(str(response.data["results"][0]["id"]), str(self.sync_record.id))

"""factory_boy factories for generating test fixtures.

Usage in tests:
    vm = VMResponseFactory()
    vm_active = VMResponseFactory(status=VMState.ACTIVE)
    many = VMResponseFactory.build_batch(5)

    server = ServerStubFactory()          # mimics openstacksdk server obj
    image  = ImageStubFactory()           # mimics openstacksdk image obj
    task   = TaskResponseFactory()        # TaskResponse Pydantic model
"""

import types
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import factory

from app.schemas.enums import TaskStatus, VMState
from app.schemas.flavor import FlavorResponse
from app.schemas.image import ImageResponse
from app.schemas.task import TaskResponse
from app.schemas.vms import AddressInfo, VMResponse


class AddressInfoFactory(factory.Factory):
    class Meta:
        model = AddressInfo

    version = 4
    addr = factory.Sequence(lambda n: f"10.0.{n // 255}.{n % 255}")
    type = "fixed"


class VMResponseFactory(factory.Factory):
    class Meta:
        model = VMResponse

    id = factory.Sequence(lambda n: f"vm-{n:08x}-0000-0000-0000-000000000000")
    name = factory.Sequence(lambda n: f"vm-{n:04d}")
    status = VMState.ACTIVE
    flavor_id = "m1.medium"
    flavor_name = "m1.medium"
    image_id = "img-ubuntu-2204"
    image_name = "ubuntu-22.04-lts"
    addresses = factory.LazyAttribute(
        lambda _: {"default-network": [AddressInfoFactory()]},
    )
    key_name = "ops-key"
    security_groups = factory.List(["default"])
    metadata = factory.Dict({"env": "test", "owner": "ci"})
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = None
    availability_zone = "nova"


class FlavorResponseFactory(factory.Factory):
    class Meta:
        model = FlavorResponse

    id = factory.Sequence(lambda n: f"flavor-{n}")
    name = factory.Sequence(lambda n: f"flavor-{n}")
    vcpus = 4
    ram_mb = 8192
    disk_gb = 80
    is_public = True
    description = None


class ImageResponseFactory(factory.Factory):
    class Meta:
        model = ImageResponse

    id = factory.Sequence(lambda n: f"img-{n:08x}")
    name = factory.Sequence(lambda n: f"test-image-{n}")
    status = "active"
    size_bytes = 2_000_000_000
    min_disk_gb = 20
    min_ram_mb = 1024
    visibility = "public"
    os_distro = "ubuntu"
    os_version = "22.04"
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))


class TaskResponseFactory(factory.Factory):
    """Builds a TaskResponse Pydantic model with a unique task_id per instance."""

    class Meta:
        model = TaskResponse

    task_id = factory.LazyFunction(uuid.uuid4)
    status = TaskStatus.PENDING
    operation = "mock_op"
    created_at = datetime(2024, 1, 1, tzinfo=UTC)
    updated_at = datetime(2024, 1, 1, tzinfo=UTC)


class ServerStubFactory(factory.Factory):
    """Creates a SimpleNamespace that mimics an openstacksdk compute server object.

    All attributes match what ``_server_to_response`` expects.  Override any
    field per-call: ``ServerStubFactory(id="vm-abc", status="SHUTOFF")``.
    """

    class Meta:
        model = types.SimpleNamespace

    id = "vm-001"
    name = "test-vm"
    status = "ACTIVE"
    addresses = factory.LazyFunction(
        lambda: {
            "net": [
                {"version": 4, "addr": "10.0.0.1", "OS-EXT-IPS:type": "fixed"},
            ],
        },
    )
    flavor = factory.LazyFunction(lambda: {"id": "small"})
    image = factory.LazyFunction(lambda: {"id": "img-001"})
    key_name = "my-key"
    security_groups = factory.LazyFunction(lambda: [{"name": "default"}])
    metadata = factory.LazyFunction(dict)
    created_at = "2024-01-01T00:00:00"
    updated_at = None
    host_id = "host-001"
    availability_zone = "nova"


class FlavorStubFactory(factory.Factory):
    """Creates a SimpleNamespace that mimics an openstacksdk compute flavor object.

    All attributes match what ``ComputeClient.list_flavors`` expects.  Override any
    field per-call: ``FlavorStubFactory(id="m1.xlarge", vcpus=16, ram=32768)``.
    """

    class Meta:
        model = types.SimpleNamespace

    id = "flavor-001"
    name = "m1.small"
    vcpus = 2
    ram = 4096
    disk = 40
    is_public = True


class ImageStubFactory(factory.Factory):
    """Creates a SimpleNamespace that mimics an openstacksdk Glance image object.

    All attributes match what ``ImageClient.list_images`` expects.  Override any
    field per-call: ``ImageStubFactory(id="img-abc", status="deactivated")``.
    Set ``get.side_effect`` after construction to simulate corrupt images.
    """

    class Meta:
        model = types.SimpleNamespace

    id = "img-001"
    name = "ubuntu"
    status = "active"
    size = 1_000_000
    min_disk = 20
    min_ram = 1024
    visibility = "public"
    created_at = "2024-01-01T00:00:00"
    # .get(key, default) is called for os_distro / os_version
    get = factory.LazyFunction(lambda: MagicMock(return_value=None))

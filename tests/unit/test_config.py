"""Unit tests for app.core.config."""

from app.core.config import Settings


def test_openstack_conn_kwargs_contains_all_fields():
    settings = Settings(
        openstack_auth_url="https://keystone.test/v3",
        openstack_username="test-user",
        openstack_password="test-pass",
        openstack_project_name="test-project",
        openstack_project_domain_name="TestDomain",
        openstack_user_domain_name="TestDomain",
        openstack_region_name="TestRegion",
    )
    kwargs = settings.openstack_conn_kwargs
    assert kwargs["auth_url"] == "https://keystone.test/v3"
    assert kwargs["username"] == "test-user"
    assert kwargs["password"] == "test-pass"
    assert kwargs["project_name"] == "test-project"
    assert kwargs["project_domain_name"] == "TestDomain"
    assert kwargs["user_domain_name"] == "TestDomain"
    assert kwargs["region_name"] == "TestRegion"

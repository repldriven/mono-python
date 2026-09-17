import pytest
from mono_bricks import system
from mono_bricks.test_system import parse_permits, with_permit, with_test_system

CONFIG = "test_system/application-test.yml"


@pytest.fixture(autouse=True)
def service_kind():
    system.register_components(
        "test-system",
        {
            "service": system.Component(
                start=lambda ctx: {
                    "name": ctx.config["name"],
                    "handler": ctx.config["handler"],
                },
                config={"handler": system.REQUIRED, "name": system.REQUIRED},
            )
        },
    )


def test_parse_permits():
    assert parse_permits("3") == 3
    assert parse_permits(" 2 ") == 2
    for s in [None, "", "0", "-1", "x"]:
        assert parse_permits(s) is None


def test_with_permit_without_semaphore_just_runs():
    with with_permit(None):
        pass


def test_patch_supplies_what_yaml_cannot_and_test_profile_applies():
    def handler(request):
        return {"status": 200}

    def patch(defs):
        defs["app"]["handler"] = system.constant(handler)
        return defs

    with with_test_system(CONFIG, patch) as sys:
        service = system.instance(sys, "app", "service")
        assert service["name"] == "test-service"
        assert service["handler"] is handler


def test_unpatched_required_component_fails():
    with pytest.raises(system.DefinitionError, match="app.handler"):
        with with_test_system(CONFIG):
            pass

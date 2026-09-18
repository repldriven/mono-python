import pytest
from mono_bricks import system
from mono_bricks.test_system import started

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


def test_patch_supplies_what_yaml_cannot_and_test_profile_applies():
    def handler(request):
        return {"status": 200}

    def patch(defs):
        defs["app"]["handler"] = system.constant(handler)
        return defs

    with started(CONFIG, patch) as sys:
        service = system.instance(sys, "app", "service")
        assert service["name"] == "test-service"
        assert service["handler"] is handler


def test_unpatched_required_component_fails():
    with pytest.raises(system.DefinitionError, match="app.handler"):
        with started(CONFIG):
            pass

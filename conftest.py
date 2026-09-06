import pycares
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(scope="session", autouse=True)
def initialize_dns_cleanup_worker() -> None:
    """Initialize pycares' process-wide worker before per-test leak checks."""
    # Since 4.9, closing the first channel starts a shared daemon that safely
    # destroys channels for the lifetime of the process. It is library state,
    # not an integration-owned thread. Keep HA's per-test cleanup checks intact
    # so any additional threads, tasks and timers still fail verification.
    if hasattr(pycares.Channel, "close"):
        pycares.Channel(event_thread=False).close()

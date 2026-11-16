import pytest

import config


@pytest.fixture(autouse=True, scope="session")
def sample_area():
    """
    Every test runs in the made-up sample area, not the real study
    area, so changing the real study area in config.py cannot break
    the tests.
    """
    config.use_sample_area()

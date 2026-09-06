from __future__ import annotations

from datetime import date

import pytest

from wallcal.devices import DEVICES, Device

TODAY = date(2026, 9, 6)  # a Sunday, inside every span below
SPAN_START = date(2026, 9, 1)
SPAN_END = date(2026, 11, 30)


@pytest.fixture(params=list(DEVICES.values()), ids=list(DEVICES))
def device(request: pytest.FixtureRequest) -> Device:
    return request.param

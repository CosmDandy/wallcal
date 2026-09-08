"""The access log: one JSON line per request, with the caller in it."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from wallcal import logs
from wallcal.app import app

SPAN = "f=2026-01-01&t=2026-12-31"


def only(caplog: pytest.LogCaptureFixture) -> dict[str, object]:
    records = [r for r in caplog.records if r.name == logs.LOGGER]
    assert len(records) == 1, f"expected one line, got {len(records)}"
    return dict(json.loads(records[0].message))


def test_a_served_wallpaper_is_logged_with_the_caller(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO, logger=logs.LOGGER)
    with TestClient(app) as client:
        caplog.clear()
        client.get(f"/w/span.png?{SPAN}", headers={"user-agent": "Shortcuts/2660.7"})

    line = only(caplog)
    assert line["path"] == "/w/span.png"
    assert line["status"] == 200
    assert line["query"] == SPAN
    assert line["ua"] == "Shortcuts/2660.7"
    assert line["ip"]  # the test client reports one; the value itself is the transport's
    assert isinstance(line["ms"], int)
    assert isinstance(line["bytes"], int) and line["bytes"] > 1000


def test_a_refused_request_is_logged_too(caplog: pytest.LogCaptureFixture):
    """A 400 is exactly the line worth having: someone is hitting a broken link."""
    caplog.set_level(logging.INFO, logger=logs.LOGGER)
    with TestClient(app) as client:
        caplog.clear()
        client.get("/w/span.png?f=today&t=9999y")

    assert only(caplog)["status"] == 400


def test_a_long_query_is_truncated(caplog: pytest.LogCaptureFixture):
    """A quote can be paragraphs long; the log is not the place to keep it."""
    caplog.set_level(logging.INFO, logger=logs.LOGGER)
    with TestClient(app) as client:
        caplog.clear()
        client.get(f"/w/span.png?{SPAN}&qt={'x' * 600}")

    query = only(caplog)["query"]
    assert isinstance(query, str)
    assert len(query) == logs.QUERY_LIMIT


def test_every_line_is_one_json_object(caplog: pytest.LogCaptureFixture):
    """`docker logs | jq` has to work, so nothing may span two lines."""
    caplog.set_level(logging.INFO, logger=logs.LOGGER)
    with TestClient(app) as client:
        caplog.clear()
        client.get("/healthz")
        client.get("/")

    records = [r for r in caplog.records if r.name == logs.LOGGER]
    assert len(records) == 2
    for record in records:
        assert "\n" not in record.message
        json.loads(record.message)


def test_a_request_for_another_domain_is_refused(monkeypatch: pytest.MonkeyPatch):
    """Only the domain the service is deployed on may address it.

    Without this a page on another site can point a browser at the container's
    address and read the response as its own.
    """
    from fastapi import FastAPI
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from starlette.testclient import TestClient as RawClient

    guarded = FastAPI()
    guarded.add_middleware(TrustedHostMiddleware, allowed_hosts=["wallcal.example.com"])

    @guarded.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    with RawClient(guarded, base_url="http://wallcal.example.com") as client:
        assert client.get("/healthz").status_code == 200
    with RawClient(guarded, base_url="http://elsewhere.test") as client:
        assert client.get("/healthz").status_code == 400


def test_the_domain_defaults_to_accepting_anything():
    """A laptop has no domain; the default must not lock the developer out."""
    from wallcal.app import ALLOWED_HOSTS

    assert ALLOWED_HOSTS == ["*"]


def test_a_coordinate_is_blunted_in_the_log(caplog: pytest.LogCaptureFixture):
    """The image keeps the two decimals it was asked for; the log keeps a town."""
    caplog.set_level(logging.INFO, logger=logs.LOGGER)
    with TestClient(app) as client:
        caplog.clear()
        client.get(f"/w/span.png?{SPAN}&sky=both&lat=51.51&lon=-0.13")

    query = only(caplog)["query"]
    assert isinstance(query, str)
    assert "lat=51.5" in query and "lat=51.51" not in query
    assert "lon=-0.1" in query and "lon=-0.13" not in query


@pytest.mark.parametrize(
    "pair",
    [
        "lat=51.5074&lon=-0.1277",
        "lat=+51.5074&lon=-0.1277",  # a literal plus is a space once decoded
        "lat=51%2E5074&lon=-0%2E1277",  # ...and an encoded point hides itself
    ],
)
def test_a_coordinate_is_blunted_however_it_was_written(
    caplog: pytest.LogCaptureFixture, pair: str
):
    """The endpoint takes all three spellings, so the log has to blunt all three."""
    caplog.set_level(logging.INFO, logger=logs.LOGGER)
    with TestClient(app) as client:
        caplog.clear()
        assert client.get(f"/w/span.png?{SPAN}&sky=sun&{pair}").status_code == 200

    query = only(caplog)["query"]
    assert isinstance(query, str)
    assert "lat=51.5&lon=-0.1" in query
    assert "5074" not in query and "1277" not in query

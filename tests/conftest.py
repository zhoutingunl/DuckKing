"""Protocol fixtures use one authenticated visitor; access tests start anonymously."""

import pytest
from fastapi.testclient import TestClient

from duckking.room_access import COOKIE_NAME, current_owner
from duckking.rooms import RoomRegistry


@pytest.fixture(autouse=True)
def authenticated_protocol_visitor(monkeypatch, request):
    if request.node.get_closest_marker("anonymous_rooms"):
        return
    original = TestClient.__init__

    def initialize(self, app, *args, **kwargs):
        original(self, app, *args, **kwargs)
        state = getattr(app, "state", None)
        sessions = getattr(state, "room_sessions", None)
        if sessions is None:
            return
        owner = "p" * 32
        self.cookies.set(COOKIE_NAME, sessions.encode(owner))
        # These pre-existing protocol tests intentionally exercise the same
        # visitor in rooms 1/2. Anonymous creation and denial are tested separately.
        for room in state.rooms.values():
            if room.owner is None:
                room.owner = owner

    monkeypatch.setattr(TestClient, "__init__", initialize)


@pytest.fixture
def direct_room_visitor(monkeypatch):
    """Authenticate tests that invoke handlers directly instead of using HTTP."""
    owner = "p" * 32
    original = RoomRegistry.__init__

    def initialize(registry, primary):
        original(registry, primary)
        for room in registry.rooms.values():
            room.owner = owner

    monkeypatch.setattr(RoomRegistry, "__init__", initialize)
    token = current_owner.set(owner)
    try:
        yield owner
    finally:
        current_owner.reset(token)

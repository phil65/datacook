"""Fixtures for the app (Qt) tests: an AppController on a FakeSession, offscreen."""

import os
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from datacook.app.controllers import AppController
from datacook.app.settings import AppSettings
from datacook.app.testing import FakeSession


if TYPE_CHECKING:
    from collections.abc import Iterator


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def frame(n: int = 3, col: str = "a") -> pd.DataFrame:
    return pd.DataFrame({col: list(range(n))})


def drain(app: AppController) -> None:
    """Deliver everything queued in the bridge (GUI thread), until nothing is left."""
    for _ in range(20):
        if not app.bridge.pending():
            return
        app.bridge.flush()
    msg = "bridge does not settle"
    raise AssertionError(msg)


def check_invariant(app: AppController) -> None:
    """Memory policy: views hold full frames only of pinned nodes."""
    assert app.held_ids() <= app.pins.pinned_ids()


@pytest.fixture
def fake() -> FakeSession:
    return FakeSession()


@pytest.fixture
def app(qapp, fake: FakeSession) -> Iterator[AppController]:
    controller = AppController(fake, AppSettings(selection_debounce_ms=0, preview_rows=10))
    yield controller
    controller.close()
    assert fake.pin_counts() == {}


@pytest.fixture(autouse=True)
def no_modal_close_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsaved changes are discarded without a modal question (close, new, open)."""
    from datacook.app.controllers.project import ProjectController

    monkeypatch.setattr(ProjectController, "_ask_save_changes", lambda _self: "discard")
    monkeypatch.setattr(ProjectController, "_confirm_discard", lambda _self: True)

"""App settings (pydantic, JSON in the platformdirs config dir; Qt-free)."""

import logging
import os
from typing import TYPE_CHECKING

import platformdirs
from pydantic import BaseModel, ConfigDict, Field, ValidationError


if TYPE_CHECKING:
    import pathlib


logger = logging.getLogger(__name__)


def default_path() -> pathlib.Path:
    return platformdirs.user_config_path("DataCook", appauthor=False) / "settings.json"


class AppSettings(BaseModel):
    """User settings; `AppState.settings` holds the active (frozen) instance."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    preview_rows: int = Field(200, ge=1)
    """Rows computed / shown for a params preview."""
    selection_debounce_ms: int = Field(80, ge=0)
    """Selecting a node that is not cached starts computing after this rest time."""
    preview_debounce_ms: int = Field(200, ge=0)
    """Debounce of the params form (`PydanticForm`) before a preview starts."""
    code_debounce_ms: int = Field(600, ge=0)
    memory_budget: int | None = None
    """Frame cache budget in bytes (`None`: engine default, 25 % of RAM)."""
    compute_threads: int = Field(default_factory=lambda: min(4, os.cpu_count() or 1), ge=1)
    view_threads: int = Field(2, ge=1)
    color_values: bool = True
    language: str | None = None
    """`None`: system language."""
    recent_files: tuple[str, ...] = ()
    recipe_folder: str | None = None
    """Recipe library folder (`None`: `recipes` in the user data dir)."""

    @classmethod
    def load(cls, path: pathlib.Path | None = None) -> AppSettings:
        """Read the settings file; defaults if it is missing or invalid."""
        path = path or default_path()
        try:
            return cls.model_validate_json(path.read_bytes())
        except FileNotFoundError:
            return cls()
        except (OSError, ValidationError, ValueError) as e:
            logger.warning("ignoring invalid settings file %s: %s", path, e)
            return cls()

    def save(self, path: pathlib.Path | None = None) -> None:
        path = path or default_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

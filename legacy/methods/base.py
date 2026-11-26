from __future__ import annotations

import pydantic


class BaseModel(pydantic.BaseModel):
    def to_dict(self):
        return self.model_dump()

"""Fast JSON responses (orjson) that also handle Decimal money values."""

from decimal import Decimal
from typing import Any

import orjson
from starlette.responses import JSONResponse


def _default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, set | frozenset):
        return list(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


class AppJSONResponse(JSONResponse):
    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        return orjson.dumps(content, default=_default, option=orjson.OPT_NON_STR_KEYS | orjson.OPT_UTC_Z)

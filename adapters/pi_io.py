"""Pi adapter: currently uses pygame event stream + keyboard fallback for parity."""

from __future__ import annotations

from typing import Callable, Tuple

from adapters.pc_io import PCIOAdapter


class PIIOAdapter(PCIOAdapter):
    """GPIO/I2C integration can be layered later without touching shared renderer/controller."""

    def __init__(self, map_pos: Callable[[Tuple[int, int]], Tuple[int, int]]):
        super().__init__(map_pos)

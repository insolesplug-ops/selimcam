"""Pi adapter. Uses pygame touch events + optional keyboard fallback + future GPIO bridge."""

from __future__ import annotations

from platform.pc_io import PCIOAdapter


class PIIOAdapter(PCIOAdapter):
    """Current implementation keeps parity with PC mapping; GPIO hooks can be added without UI divergence."""

    pass

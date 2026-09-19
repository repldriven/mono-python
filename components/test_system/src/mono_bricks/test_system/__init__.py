"""Systems under test.

`started` loads config for the test profile, builds definitions, optionally
patches them, and starts the system for the duration of the block.
"""

from mono_bricks.test_system.core import started

__all__ = ["started"]

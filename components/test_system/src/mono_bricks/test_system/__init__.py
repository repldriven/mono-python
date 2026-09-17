"""Systems under test.

`with_test_system` loads config for the test profile, builds definitions,
optionally patches them, and starts the system for the duration of the block.

When TEST_SYSTEM_PERMITS is set, each test system holds one of that many
permits from start to stop, so at most that many are up at once. The bound
is per process: under pytest-xdist each worker has its own, so the effective
bound is workers times permits.
"""

from mono_bricks.test_system.core import parse_permits, with_permit, with_test_system

__all__ = ["parse_permits", "with_permit", "with_test_system"]

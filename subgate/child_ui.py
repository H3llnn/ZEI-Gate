"""Compatibility alias; implementation lives in ZEI-ForceSubs."""
import sys
from zei_forcesubs import child_ui as _implementation

sys.modules[__name__] = _implementation

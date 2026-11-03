"""Compatibility alias; implementation lives in ZEI-Payment."""
import sys
from zei_payment import saweria as _implementation

sys.modules[__name__] = _implementation

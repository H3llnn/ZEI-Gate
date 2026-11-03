"""Compatibility alias; implementation lives in ZEI-Payment."""
import sys
from zei_payment import payment_ui as _implementation

sys.modules[__name__] = _implementation

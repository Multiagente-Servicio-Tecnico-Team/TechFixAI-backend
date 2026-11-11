"""Spanish compatibility alias for the active support_tools module."""
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module(".support_tools", __package__)

"""Legacy import path for the active Descentralizado support node."""
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module(".support", __package__)

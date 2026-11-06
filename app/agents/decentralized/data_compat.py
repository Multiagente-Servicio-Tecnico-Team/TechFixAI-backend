"""Compatibilidad: la implementacion vive en compatibility.data_compat."""
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("app.agents.decentralized.compatibility.data_compat")

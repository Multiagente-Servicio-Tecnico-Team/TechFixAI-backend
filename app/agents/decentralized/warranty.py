"""Compatibilidad: la implementacion vive en agents.warranty."""
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("app.agents.decentralized.agents.warranty")

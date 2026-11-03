"""Compatibilidad: la implementacion vive en operations.payment_operations."""
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("app.agents.decentralized.operations.payment_operations")

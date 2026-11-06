"""Compatibilidad: la implementacion vive en policies.policy."""
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("app.agents.decentralized.policies.policy")

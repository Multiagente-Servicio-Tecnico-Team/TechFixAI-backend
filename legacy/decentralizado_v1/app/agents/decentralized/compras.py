from app.agents.procurement import procurement_node as _procurement_node


def procurement_node(state):
    return _procurement_node(state)
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module(".purchasing", __package__)

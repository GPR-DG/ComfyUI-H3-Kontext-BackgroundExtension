"""Add only missing H3 background capabilities to an existing H3 installation."""
from .registration import select_core

_core_classes, _core_names, CORE_PROVIDER_MODE = select_core()

from .h3_kontext_bridge import NODE_CLASS_MAPPINGS as _kontext_classes
from .h3_kontext_bridge import NODE_DISPLAY_NAME_MAPPINGS as _kontext_names

NODE_CLASS_MAPPINGS = {**_core_classes, **_kontext_classes}
NODE_DISPLAY_NAME_MAPPINGS = {**_core_names, **_kontext_names}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']

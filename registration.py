"""Select one pinned background provider; never import old runner/API packages."""
import hashlib
import importlib
import json
from pathlib import Path
import tokenize

CORE_NAMES = frozenset(('H3CBackgroundTaskStart', 'H3CBestBackgroundFrame',
    'H3CBackgroundResolve', 'H3CBackgroundWashClaim', 'H3CBackgroundAttachClean',
    'H3CBackgroundTaskCleanup'))
K_NAMES = frozenset(('H3KBackgroundResolve', 'H3KBackgroundWashClaim',
    'H3KBackgroundFinish', 'H3KBackgroundSource', 'H3KStageGuard', 'H3KRecipe',
    'H3KPromptCapture', 'H3KStagePreview'))
FEATURE_ENTRY_SHA256 = '4b392c9efafe754233e1d91c24815c9a1bec6ee5f97a226f4c554b131c546eca'
ROOT = Path(__file__).resolve().parent


def source_hash(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def verify_core(root):
    pins = json.loads((ROOT / 'h3_kontext_bridge/core-required-sha256.json').read_text(encoding='utf-8'))
    for name, expected in pins.items():
        path = root / name
        if not path.is_file() or source_hash(path) != expected:
            raise RuntimeError('Unsupported H3 background provider: source mismatch in ' + name)


def has_kontext_classes(path):
    if not path.is_file():
        return False
    with tokenize.open(path) as source:
        text = source.read()
    return any('class ' + name in text for name in K_NAMES)


def active_plugins():
    import folder_paths
    try:
        from comfy.cli_args import args
    except ModuleNotFoundError as error:
        if error.name not in ('comfy', 'comfy.cli_args'):
            raise
        args = None
    for folder in folder_paths.get_folder_paths('custom_nodes'):
        path = Path(folder)
        if not path.is_dir():
            continue
        for plugin in path.iterdir():
            if (not plugin.is_dir() or plugin.name.endswith('.disabled')
                    or plugin.resolve() == ROOT or not (plugin / '__init__.py').is_file()):
                continue
            if (args is not None and args.disable_all_custom_nodes
                    and plugin.name not in args.whitelist_custom_nodes):
                continue
            yield plugin.resolve()


def select_core():
    import nodes
    registry = nodes.NODE_CLASS_MAPPINGS
    if K_NAMES.intersection(registry):
        raise RuntimeError('Another H3K/Kontext provider is already registered; use one Kontext owner only')
    loaded = {name: registry[name] for name in CORE_NAMES if name in registry}
    modules = {importlib.import_module(cls.__module__) for cls in loaded.values()}
    if len(modules) > 1:
        raise RuntimeError('Multiple/mixed H3 background class providers are unsupported')
    module = next(iter(modules), None)
    providers = {Path(module.__file__).resolve().parent} if module is not None else set()
    for plugin in active_plugins():
        # These layouts are known H3K owners, not background-only Core providers.
        paths = [plugin / 'nodes.py', plugin / 'h3_kontext_bridge/nodes.py',
            plugin / 'h3_adapter_bundle/h3_kontext_bridge/nodes.py']
        if any(has_kontext_classes(path) for path in paths):
            raise RuntimeError('Another installed H3K/Kontext package would register the same nodes: ' + plugin.name)
        if (plugin / 'h3_background_nodes.py').is_file():
            providers.add(plugin)
    if len(providers) > 1:
        raise RuntimeError('Multiple H3 background providers found; no classes were overwritten')
    if providers:
        provider = next(iter(providers))
        verify_core(provider)
        if module is not None:
            for name, cls in loaded.items():
                if cls is not getattr(module, name, None):
                    raise RuntimeError('Unsupported H3 background class identity: ' + name)
            missing = CORE_NAMES.difference(loaded)
            return ({name: getattr(module, name) for name in missing},
                {name: module.NODE_DISPLAY_NAME_MAPPINGS[name] for name in missing}, 'reuse-loaded-core')
        entry = provider / '__init__.py'
        if source_hash(entry) != FEATURE_ENTRY_SHA256:
            raise RuntimeError('Unsupported H3 background provider entry; cannot reserve future registrations')
        # ComfyUI can load this extension first. The verified original feature
        # entry will register all six Core classes later; do not claim them here.
        return {}, {}, 'defer-to-installed-core'
    from .background_core.h3_background_nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
    verify_core(ROOT / 'background_core')
    return dict(NODE_CLASS_MAPPINGS), dict(NODE_DISPLAY_NAME_MAPPINGS), 'bundled-background-only'

"""Registration boundary tests; real pinned Core/H3K classes, no neural inference."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

# Load native extensions before scoped sys.modules restoration; NumPy/Torch
# cannot be unloaded and reinitialized repeatedly inside one interpreter.
import cv2
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
CORE_NAMES = {'H3CBackgroundTaskStart', 'H3CBestBackgroundFrame', 'H3CBackgroundResolve',
    'H3CBackgroundWashClaim', 'H3CBackgroundAttachClean', 'H3CBackgroundTaskCleanup'}
K_NAMES = {'H3KBackgroundResolve', 'H3KBackgroundWashClaim', 'H3KBackgroundFinish',
    'H3KBackgroundSource', 'H3KStageGuard', 'H3KRecipe', 'H3KPromptCapture', 'H3KStagePreview'}
ENTRY_HASH = '4b392c9efafe754233e1d91c24815c9a1bec6ee5f97a226f4c554b131c546eca'

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path / '__init__.py',
        submodule_search_locations=[str(path)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def load_core(path, name):
    package = types.ModuleType(name)
    package.__path__ = [str(path)]
    sys.modules[name] = package
    spec = importlib.util.spec_from_file_location(name + '.h3_background_nodes', path / 'h3_background_nodes.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.custom = Path(self.temp.name)
        self.registry = {'ExistingOldNode': object()}
        host = types.ModuleType('nodes')
        host.NODE_CLASS_MAPPINGS = self.registry
        folders = types.ModuleType('folder_paths')
        folders.get_folder_paths = lambda key: [str(self.custom)] if key == 'custom_nodes' else []
        self.env = patch.dict(sys.modules, {'nodes': host, 'folder_paths': folders})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.number = len([n for n in sys.modules if n.startswith('_extension_test_')])

    def plugin(self):
        self.assertTrue((ROOT / '__init__.py').is_file(), 'Independent plugin entrypoint is missing')
        return load(ROOT, '_extension_test_' + str(self.number))

    def provider(self, name='ComfyUI-H3HardCutRunner', crlf=False):
        target = self.custom / name
        target.mkdir()
        for item in (ROOT / 'background_core').glob('*.py'):
            if item.name != '__init__.py':
                data = item.read_bytes().replace(b'\r\n', b'\n')
                (target / item.name).write_bytes(data.replace(b'\n', b'\r\n') if crlf else data)
        # Exact feature entrypoint is a test fixture, not imported by this helper.
        entry = ROOT / 'tests/fixtures/core-feature-entry.txt'
        data = entry.read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(data).hexdigest(), ENTRY_HASH)
        (target / '__init__.py').write_bytes(data.replace(b'\n', b'\r\n') if crlf else data)
        return target

    def register_provider(self, path, names=CORE_NAMES):
        module = load_core(path, '_real_core_' + str(self.number))
        self.registry.update({n: module.NODE_CLASS_MAPPINGS[n] for n in names})
        return module

    def test_main_adds_only_14_background_nodes_without_overwriting(self):
        old = dict(self.registry)
        plugin = self.plugin()
        self.assertEqual(set(plugin.NODE_CLASS_MAPPINGS), CORE_NAMES | K_NAMES)
        self.assertEqual(self.registry, old)
        self.assertFalse(hasattr(plugin, 'WEB_DIRECTORY'))
        self.assertFalse({'H3StageGuard', 'H3StagePreview', 'H3CBackgroundFinish'} & plugin.NODE_CLASS_MAPPINGS.keys())

    def test_registered_feature_reuses_identity_and_does_not_load_bundled_state(self):
        source = self.provider()
        core = self.register_provider(source)
        before = dict(self.registry)
        plugin = self.plugin()
        self.assertEqual(set(plugin.NODE_CLASS_MAPPINGS), K_NAMES)
        self.registry.update(plugin.NODE_CLASS_MAPPINGS)
        k = sys.modules[plugin.__name__ + '.h3_kontext_bridge.nodes']
        self.assertIs(k.core(), core)
        for name, cls in before.items():
            self.assertIs(self.registry[name], cls)
        self.assertNotIn(plugin.__name__ + '.background_core.h3_background_nodes', sys.modules)

    def test_extension_first_reserves_all_feature_names_until_original_loads(self):
        source = self.provider()
        plugin = self.plugin()
        self.assertEqual(set(plugin.NODE_CLASS_MAPPINGS), K_NAMES)
        self.registry.update(plugin.NODE_CLASS_MAPPINGS)
        core = self.register_provider(source)
        k = sys.modules[plugin.__name__ + '.h3_kontext_bridge.nodes']
        self.assertIs(k.core(), core)
        task = self.registry['H3CBackgroundTaskStart']().run()[0]
        try:
            self.assertIsInstance(task, core.BackgroundTaskHandle)
        finally:
            task.cleanup()

    def test_partial_registered_provider_fills_from_same_module(self):
        source = self.provider()
        core = self.register_provider(source, {'H3CBackgroundResolve'})
        plugin = self.plugin()
        self.assertEqual(set(plugin.NODE_CLASS_MAPPINGS), K_NAMES | (CORE_NAMES - {'H3CBackgroundResolve'}))
        for name in CORE_NAMES - {'H3CBackgroundResolve'}:
            self.assertIs(plugin.NODE_CLASS_MAPPINGS[name], core.NODE_CLASS_MAPPINGS[name])

    def test_changed_core_bytes_rejected_without_modifying_registry(self):
        source = self.provider()
        core = self.register_provider(source)
        before = dict(self.registry)
        (source / 'h3_background_cache.py').write_bytes(b'# mismatched version\n')
        with self.assertRaisesRegex(RuntimeError, 'mismatch|unsupported'):
            self.plugin()
        self.assertEqual(self.registry, before)

    def test_unrecognized_feature_entry_rejected(self):
        source = self.provider()
        (source / '__init__.py').write_text('NODE_CLASS_MAPPINGS = {}\n')
        with self.assertRaisesRegex(RuntimeError, 'entry|unsupported'):
            self.plugin()

    def test_multiple_feature_providers_rejected(self):
        self.provider('CoreOne')
        self.provider('CoreTwo')
        with self.assertRaisesRegex(RuntimeError, 'multiple|Multiple'):
            self.plugin()

    def test_disabled_feature_is_not_an_active_provider(self):
        self.provider('ComfyUI-H3HardCutRunner.disabled')
        self.assertEqual(set(self.plugin().NODE_CLASS_MAPPINGS), CORE_NAMES | K_NAMES)

    def test_crlf_feature_is_supported_without_weakening_source_check(self):
        source = self.provider(crlf=True)
        self.register_provider(source)
        self.assertEqual(set(self.plugin().NODE_CLASS_MAPPINGS), K_NAMES)

    def test_mixed_registered_providers_rejected(self):
        first = self.provider('First')
        second = self.provider('Second')
        self.register_provider(first, {'H3CBackgroundResolve'})
        other = load_core(second, '_other_core_' + str(self.number))
        self.registry['H3CBackgroundTaskStart'] = other.H3CBackgroundTaskStart
        with self.assertRaisesRegex(RuntimeError, 'multiple|Multiple|mixed'):
            self.plugin()

    def test_existing_h3k_owner_is_not_overwritten(self):
        self.registry['H3KStageGuard'] = object()
        before = dict(self.registry)
        with self.assertRaisesRegex(RuntimeError, 'H3K|Kontext'):
            self.plugin()
        self.assertEqual(self.registry, before)

    def test_pending_h3k_owner_on_disk_is_rejected(self):
        sibling = self.custom / 'ComfyUI-H3-Kontext-BackgroundBridge'
        sibling.mkdir()
        (sibling / '__init__.py').write_text('from .nodes import NODE_CLASS_MAPPINGS\n')
        (sibling / 'nodes.py').write_text('class H3KStageGuard: pass\n')
        with self.assertRaisesRegex(RuntimeError, 'H3K|Kontext'):
            self.plugin()

    def test_valid_python_encoding_cookie_in_unrelated_plugin_does_not_block_loading(self):
        sibling = self.custom / 'UnrelatedLatin1Plugin'
        sibling.mkdir()
        (sibling / '__init__.py').write_text('from .nodes import NODE_CLASS_MAPPINGS\n')
        source = '# coding: latin-1\n# café\nNODE_CLASS_MAPPINGS = {}\n'.encode('latin-1')
        compile(source, 'nodes.py', 'exec')
        (sibling / 'nodes.py').write_bytes(source)
        self.assertEqual(set(self.plugin().NODE_CLASS_MAPPINGS), CORE_NAMES | K_NAMES)

    def test_non_utf8_h3k_provider_is_still_rejected(self):
        sibling = self.custom / 'Latin1KontextProvider'
        sibling.mkdir()
        (sibling / '__init__.py').write_text('from .nodes import NODE_CLASS_MAPPINGS\n')
        (sibling / 'nodes.py').write_bytes('# coding: latin-1\n# café\nclass H3KStageGuard: pass\n'.encode('latin-1'))
        with self.assertRaisesRegex(RuntimeError, 'H3K|Kontext'):
            self.plugin()

    def test_pinned_source_files_and_core_contract_remain_exact(self):
        plugin = self.plugin()
        manifest = json.loads((ROOT / 'UPSTREAM-MANIFEST.json').read_text())
        self.assertEqual(len(manifest['files']), 8)
        for row in manifest['files']:
            data = (ROOT / row['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'], row['path'])
            self.assertEqual(hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest(), row['git_blob_sha'])
        self.registry.update(plugin.NODE_CLASS_MAPPINGS)
        module = sys.modules[plugin.__name__ + '.h3_kontext_bridge.nodes'].core()
        self.assertEqual(module.H3CBackgroundAttachClean.RETURN_TYPES, ('BACKGROUND_VIEW', 'IMAGE', 'STRING'))

if __name__ == '__main__':
    unittest.main()

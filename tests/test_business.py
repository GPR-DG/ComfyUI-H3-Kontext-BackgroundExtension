"""Real background algorithms/SQLite/Torch; identity-canvas CPU fixtures only."""
from concurrent.futures import ThreadPoolExecutor
import importlib
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

import numpy as np
import torch

from test_registration import ROOT, load


class BusinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        host = types.ModuleType('nodes')
        host.NODE_CLASS_MAPPINGS = {}
        folders = types.ModuleType('folder_paths')
        folders.get_folder_paths = lambda key: []
        env = patch.dict(sys.modules, {'nodes': host, 'folder_paths': folders})
        env.start()
        self.addCleanup(env.stop)
        self.plugin = load(ROOT, '_background_business_test')
        self.classes = self.plugin.NODE_CLASS_MAPPINGS
        host.NODE_CLASS_MAPPINGS.update(self.classes)
        self.k = importlib.import_module(self.plugin.__name__ + '.h3_kontext_bridge.nodes')
        self.core = self.k.core()
        # Geometry selection uses the real official list in executor tests. These
        # unit fixtures exercise real resampling at identity to keep tests small.
        geometry = patch.object(self.k, 'geometry', side_effect=lambda h, w:
            dict(h=h, w=w, bh=h, bw=w, scale=1., x=0., y=0.))
        geometry.start()
        self.addCleanup(geometry.stop)

    def task(self, label='video', database=':memory:'):
        task = self.classes['H3CBackgroundTaskStart']().run(label, database)[0]
        self.addCleanup(task.cleanup)
        return task

    def candidate(self, task, seed=42, shot=1):
        pixels = torch.rand((1, 32, 48, 3), generator=torch.Generator().manual_seed(seed))
        return self.classes['H3CBestBackgroundFrame']().run(task, pixels, shot, False, 32, 2,
            person_masks=torch.zeros((1, 32, 48)))[0]

    def start(self, task=None, seed=42, revision='recipe-1'):
        task = task or self.task()
        candidate = self.candidate(task, seed)
        view = self.k.H3KBackgroundResolve().run(task, candidate, revision)[0]
        token = self.k.H3KBackgroundWashClaim().run(task, view)[0]
        pixels, canvas = self.k.H3KBackgroundSource().run(task, view, token)
        return task, candidate, view, token, pixels, canvas

    def finish(self, task, candidate, view, token, pixels, canvas):
        b, original, _ = self.k.H3KStageGuard().run(task, view, token, pixels, canvas, 'kontext')
        self.k.H3KPromptCapture().run(task, view, ['empty room; CPU test fixture'])
        _, z, _ = self.k.H3KStageGuard().run(task, view, token, b, canvas, 'z_image')
        return self.k.H3KBackgroundFinish().run(task, view, z, token, original)['result']

    def test_real_core_chain_commits_ready_only_after_both_stages(self):
        args = self.start()
        task, candidate, view, token, pixels, canvas = args
        self.assertEqual(task.cache.get(view.view_id).state, 'PENDING')
        result = self.finish(*args)
        self.assertTrue(result[3])
        self.assertEqual(task.cache.get(view.view_id).state, 'READY')
        self.assertEqual(tuple(result[1].shape), (1, 32, 48, 3))
        self.assertTrue(torch.allclose(result[1], pixels, atol=1e-5))

    def test_failed_stage_never_ready_and_retry_reuses_claim(self):
        args = self.start()
        task, _, view, token, pixels, canvas = args
        with self.assertRaisesRegex(ValueError, 'without Kontext'):
            self.k.H3KStageGuard().run(task, view, token, pixels, canvas, 'z_image')
        with self.assertRaisesRegex(ValueError, 'Kontext completion'):
            self.k.H3KBackgroundFinish().run(task, view, pixels, token, pixels)
        self.assertEqual(task.cache.get(view.view_id).state, 'PENDING')
        self.assertEqual(self.k.H3KBackgroundWashClaim().run(task, view)[0], token)
        self.assertTrue(self.finish(*args)[3])

    def test_A_B_A_exact_recipe_reuses_ready_and_different_environment_gets_pending(self):
        args = self.start()
        task, a, view, *_ = args
        self.finish(*args)
        b = self.candidate(task, seed=123, shot=2)
        other = self.k.H3KBackgroundResolve().run(task, b, 'recipe-1')
        self.assertNotEqual(other[0].view_id, view.view_id)
        self.assertEqual(other[4], 'PENDING')
        again = self.candidate(task, seed=42, shot=3)
        hit = self.k.H3KBackgroundResolve().run(task, again, 'recipe-1')
        self.assertEqual(hit[0].view_id, view.view_id)
        self.assertTrue(hit[5])
        self.assertEqual(self.k.H3KBackgroundWashClaim().run(task, hit[0])[:2], ('', False))
        self.assertEqual(self.k.H3KBackgroundFinish().check_lazy_status(task, hit[0]), [])
        self.assertTrue(self.k.H3KBackgroundFinish().run(task, hit[0])['result'][3])

    def test_recipe_change_does_not_reuse_old_ready_result(self):
        args = self.start()
        self.finish(*args)
        task, candidate, view, *_ = args
        fresh = self.k.H3KBackgroundResolve().run(task, candidate, 'recipe-2')
        self.assertNotEqual(fresh[0].view_id, view.view_id)
        self.assertEqual(fresh[4], 'PENDING')

    def test_task_isolation_and_cleanup_release_all_local_tensor_evidence(self):
        args = self.start()
        self.finish(*args)
        task, candidate, view, *_ = args
        second = self.task()
        with self.assertRaisesRegex(ValueError, 'Cross-task'):
            self.k.H3KBackgroundResolve().run(second, candidate, 'recipe-1')
        with self.assertRaisesRegex(ValueError, 'Cross-task'):
            self.k.H3KBackgroundFinish().run(second, view)
        independent = self.k.H3KBackgroundResolve().run(second, self.candidate(second), 'recipe-1')
        self.assertEqual(independent[4], 'PENDING')
        self.assertNotEqual(task.task_id, second.task_id)
        self.classes['H3CBackgroundTaskCleanup']().run(task, None)
        self.assertTrue(task.cleaned)
        self.assertIsNone(task.cache.db)
        for name in ('exact', 'recipes', 'tokens', 'canvas', 'removed', 'washed', 'prompts'):
            self.assertFalse(task._h3k[name])
        self.assertEqual(second.cache.get(independent[0].view_id).state, 'PENDING')

    def test_altered_stage_pixels_cannot_be_attached(self):
        task, _, view, token, pixels, canvas = self.start()
        b, original, _ = self.k.H3KStageGuard().run(task, view, token, pixels, canvas, 'kontext')
        self.k.H3KPromptCapture().run(task, view, 'empty room')
        _, z, _ = self.k.H3KStageGuard().run(task, view, token, b, canvas, 'z_image')
        z.zero_()
        with self.assertRaisesRegex(ValueError, 'mismatched'):
            self.k.H3KBackgroundFinish().run(task, view, z, token, original)
        self.assertEqual(task.cache.get(view.view_id).state, 'PENDING')

    def test_sqlite_concurrent_claim_has_one_winner_and_explicit_retry(self):
        path = str(Path(self.temp.name) / 'claims.sqlite3')
        task = self.task(database=path)
        candidate = self.candidate(task)
        view = self.classes['H3CBackgroundResolve']().run(task, candidate)[0]
        barrier = threading.Barrier(4)
        def claim(_):
            cache = self.core.BackgroundCache(task.task_id, path)
            try:
                barrier.wait(timeout=10)
                return cache.claim_wash(view.view_id)
            finally:
                cache.close()
        with ThreadPoolExecutor(max_workers=4) as pool:
            tokens = list(pool.map(claim, range(4)))
        winners = [t for t in tokens if t]
        self.assertEqual(len(winners), 1)
        task.cache.release_wash(view.view_id, winners[0])
        retry = task.cache.claim_wash(view.view_id)
        self.assertTrue(retry)
        self.assertNotEqual(retry, winners[0])
        with self.assertRaisesRegex(ValueError, 'stale'):
            task.cache.attach_clean(view.view_id, candidate.image, wash_token=winners[0])
        task.cache.attach_clean(view.view_id, candidate.image, wash_token=retry)
        self.assertEqual(task.cache.get(view.view_id).state, 'READY')

if __name__ == '__main__':
    unittest.main()

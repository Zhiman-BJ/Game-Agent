"""Offline regression checks for admission, safe resume and evidence binding."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'pipeline/tools'))
from construction import TaskConstructor
from host import dump, read
from replay import pick_combined, validate_record
from scheduler import BatchScheduler, InvocationBoundaryPause


class Scheduling(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.batch = BatchScheduler.__new__(BatchScheduler)
        self.batch.batch = self.root
        self.batch.amendment = self.root / 'recovery_receipts'
        self.batch.cfg = {}
        self.batch.state = {}
        self.batch.cancel = threading.Event()
        self.batch.control = Mock(return_value={})
        self.batch.update = Mock()
        self.lane = {'task_id': 'task_1'}

    def test_pause_retains_checkpoint_and_prevents_review_or_model_call(self):
        checkpoint = self.root / 'lane_progress/task_1.json'
        saved = {'author_thread': 'existing-thread', 'effective_author_turns': 3,
                 'pending_host_replay': True, 'host_replay_candidate': {'grader': 'sha'}}
        dump(checkpoint, saved)
        self.batch.control.return_value = {'pause_new': True}
        with patch.object(TaskConstructor, 'invoke') as invoke, \
             patch.object(TaskConstructor, 'review') as review:
            with self.assertRaises(InvocationBoundaryPause):
                self.batch.invoke(self.lane, 'author', 'prompt', {})
            with self.assertRaises(InvocationBoundaryPause):
                self.batch.review(self.lane, {}, 1)
            invoke.assert_not_called()
            review.assert_not_called()
        with patch.object(TaskConstructor, 'run_lane', side_effect=InvocationBoundaryPause):
            self.batch.run_lane(self.lane)
        self.assertEqual(read(checkpoint), {**saved, 'recovery_entry_pending': True})
        self.assertEqual(self.batch.update.call_args.kwargs['status'], 'PAUSED')

    def test_admission_is_shared_and_releases_exactly_one_slot(self):
        self.batch.cfg = {'shared_admission_root': str(self.root / 'admission'),
                          'api_concurrency_per_provider': 2}
        leases = []
        try:
            leases.extend(self.batch.acquire_admission('provider_a') for _ in range(2))
            self.assertTrue(all(fd is not None for fd in leases))
            self.assertIsNone(self.batch.acquire_admission('provider_a'))
            other = BatchScheduler.__new__(BatchScheduler)
            other.cfg = self.batch.cfg
            self.assertIsNone(other.acquire_admission('provider_a'))
            os.close(leases.pop())
            released = other.acquire_admission('provider_a')
            self.assertIsNotNone(released)
            leases.append(released)
            self.assertIsNone(self.batch.acquire_admission('provider_a'))
        finally:
            for fd in leases:
                if fd is not None:
                    os.close(fd)

    def test_missing_native_home_uses_checkpoint_continuation(self):
        with patch.object(TaskConstructor, 'invoke', return_value='invoked') as invoke:
            result = self.batch.invoke(self.lane, 'author', 'prompt', {},
                                       session='old-thread', home=str(self.root/'missing'))
        self.assertEqual(result, 'invoked')
        self.assertEqual(invoke.call_args.args[4:6], (None, None))
        self.assertEqual(self.batch.update.call_args.kwargs['session_recovery']['previous_thread'],
                         'old-thread')

    def test_oversized_review_reset_is_bounded_and_archives_original(self):
        self.batch.cfg = {'review_payload_recovery': {'task_1': {'original_findings': 'findings.json'}}}
        self.batch.state = {'task_1': {'job': 'jobs/task_1/review-001'}}
        dump(self.root/'jobs/task_1/review-001/job.json', {'failure_kind': 'PAYLOAD_TOO_LARGE'})
        checkpoint = self.root/'review_resume/task_1.json'
        dump(checkpoint, {'thread_id': 'original-thread', 'before': {'grader': 'hash'}})
        original = checkpoint.read_bytes()
        with patch.object(TaskConstructor, 'review', return_value={'status': 'ACCEPTED'}) as review:
            self.assertEqual(self.batch.review(self.lane, {}, 1)['status'], 'ACCEPTED')
            review.assert_called_once()
            self.assertFalse(checkpoint.exists())
            archived = self.batch.amendment/'payload_recovery/task_1.previous_review_resume.json'
            self.assertEqual(archived.read_bytes(), original)
            # A second reset must stop before starting another model review.
            self.assertEqual(self.batch.review(self.lane, {}, 1)['status'], 'INFRA_FAILED')
            review.assert_called_once()


class EvidenceBinding(unittest.TestCase):
    def test_conflicting_canonical_verdicts_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dump(root/'final_result.json', {'status': 'PASS'})
            dump(root/'grade_result.json', {'status': 'FAIL'})
            with self.assertRaisesRegex(ValueError, 'Conflicting canonical'):
                pick_combined(root, read)

    def test_replay_reuse_requires_all_current_fingerprints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dump(root/'validators/task_1/validator_manifest.json', {})
            output = root/'output'
            valid = {'status': 'PASS', 'candidate_digest': 'candidate',
                     'grader_files': {'test.gd': 'grader'}, 'runner_sha256': 'runner',
                     'source_unchanged': True}
            actor = SimpleNamespace(read=read,
                gate=SimpleNamespace(audit_result=Mock(return_value=([], None))),
                runner=SimpleNamespace(hashes=lambda p: {}, digest=lambda h: 'candidate'))
            current = {'grader': valid['grader_files'], 'runner': 'runner'}
            dump(output/'result.json', valid)
            self.assertEqual(validate_record(actor, root, 'task_1', root/'candidate',
                                             output, 'full', current)[0], [])
            for field, bad in [('candidate_digest', 'stale'), ('grader_files', {}),
                               ('runner_sha256', 'stale'), ('source_unchanged', False)]:
                with self.subTest(field=field):
                    dump(output/'result.json', {**valid, field: bad})
                    self.assertTrue(validate_record(actor, root, 'task_1', root/'candidate',
                                                    output, 'full', current)[0])


if __name__ == '__main__':
    unittest.main()

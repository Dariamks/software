import threading
import unittest
from types import SimpleNamespace
from parallel_batch import run_parallel


class ParallelTests(unittest.TestCase):
    def test_real_overlap_and_independent_sessions(self):
        for workers in range(2, 7):
            barrier = threading.Barrier(workers)
            sessions, closed, results = [], [], []
            lock = threading.Lock()

            def factory():
                obj = SimpleNamespace()
                obj.session = SimpleNamespace(close=lambda: closed.append(obj))
                with lock:
                    sessions.append(obj)
                return obj

            def process(processor, row, **kwargs):
                barrier.wait(timeout=5)  # Sequential execution cannot pass this.
                return {"contract_no": row.contract_no}

            run_parallel([str(i) for i in range(workers * 2)], workers,
                         threading.Event(), factory, True, "reviewer", results.append, process)
            self.assertEqual(len(results), workers * 2)
            self.assertFalse(any(r.get("failed") for r in results))
            self.assertEqual(len({id(s) for s in sessions}), workers * 2)
            self.assertEqual(len(closed), workers * 2)

    def test_stop_prevents_new_contracts(self):
        stop = threading.Event()
        stop.set()
        run_parallel(["a", "b"], 2, stop, lambda: self.fail("started after stop"),
                     True, "reviewer", lambda r: self.fail("unexpected result"))

    def test_errors_do_not_abort_batch(self):
        closed, results = [], []
        def process(p, row, **kwargs):
            raise RuntimeError("test")
        run_parallel(["a", "a", "b"], 2, threading.Event(),
                     lambda: SimpleNamespace(session=SimpleNamespace(close=lambda: closed.append(1))),
                     True, "reviewer", results.append, process)
        self.assertEqual(len(results), 2)
        self.assertEqual(len(closed), 2)
        self.assertTrue(all(r.get("failed") for r in results))

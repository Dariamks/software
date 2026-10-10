"""Bounded contract concurrency; each worker owns its HTTP session."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

from batch_single_payment import InputRow, process_one


def run_parallel(contracts, workers, stop_event, processor_factory, execute,
                 reviewer_id, on_result, process=process_one):
    if workers not in range(2, 7):
        raise ValueError("并行数必须为 2～6")
    items = iter(enumerate(dict.fromkeys(contracts), 1))

    def task(index, contract):
        if stop_event.is_set():
            return None
        processor = processor_factory()
        try:
            return process(processor, InputRow(index, contract, ""), execute=execute,
                           review_user_id=reviewer_id, submit_opinion="扣款")
        finally:
            processor.session.close()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}

        def fill():
            while len(pending) < workers and not stop_event.is_set():
                item = next(items, None)
                if item is None:
                    break
                pending[pool.submit(task, *item)] = item[1]

        fill()
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                contract = pending.pop(future)
                try:
                    result = future.result()
                except Exception:
                    result = {"contract_no": contract, "failed": [
                        {"reason": "worker_failed"}]}
                if result is not None:
                    on_result(result)
            fill()

"""Background worker entrypoint (`python -m app.workers.runner`) with graceful shutdown and stale-job recovery."""
from __future__ import annotations

import asyncio
import signal
from typing import Optional

from app.config import Settings, get_settings
from app.database.session import DatabaseManager
from app.logging_config import configure_logging
from app.workers.meme_worker import MemeJobWorker


async def run_worker_loop(
    settings: Optional[Settings] = None,
    *,
    max_iterations: Optional[int] = None,
    poll_interval_seconds: float = 2.0,
) -> int:
    resolved_settings = settings or get_settings()
    logger = configure_logging(resolved_settings.log_level)
    db_manager = DatabaseManager(resolved_settings)
    if not resolved_settings.database_url.startswith("postgresql"):
        db_manager.apply_migrations_sync()

    stop_event = asyncio.Event()

    def _handle_signal(*_args: object) -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except Exception:
            pass

    processed_total = 0
    try:
        async with db_manager.session_scope() as session:
            worker = MemeJobWorker(session=session, settings=resolved_settings)
            recovered = await worker.recover_stale_generating_jobs()
            if recovered:
                logger.info(f"Recovered {recovered} interrupted meme job(s) on worker startup")

        iteration = 0
        while not stop_event.is_set():
            iteration += 1
            async with db_manager.session_scope() as session:
                worker = MemeJobWorker(session=session, settings=resolved_settings)
                res = await worker.process_single_job()
                if res is not None:
                    processed_total += 1
            if max_iterations is not None and iteration >= max_iterations:
                break
            if res is None:
                await asyncio.sleep(poll_interval_seconds)
    finally:
        await db_manager.dispose()

    return processed_total


if __name__ == "__main__":
    asyncio.run(run_worker_loop())

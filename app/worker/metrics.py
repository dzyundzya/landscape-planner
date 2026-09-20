import resource
import sys
from collections.abc import Callable
from pathlib import Path
from time import perf_counter

from anyio import to_thread
from loguru import logger


async def run_measured_operation[ResultT](
    operation: Callable[[], ResultT],
    *,
    job_id: int,
    operation_name: str,
    source_path: Path,
) -> ResultT:
    """Выполняет тяжёлую функцию в потоке и журналирует её ресурсы."""

    source_size_bytes = source_path.stat().st_size
    started_at = perf_counter()
    peak_rss_before_mb = _peak_rss_mb()
    logger.info(
        'Тяжёлая операция начата: job_id={}, operation={}, source_size_bytes={}, peak_rss_mb={:.1f}',
        job_id,
        operation_name,
        source_size_bytes,
        peak_rss_before_mb,
    )
    try:
        return await to_thread.run_sync(operation)
    finally:
        logger.info(
            'Тяжёлая операция завершена: job_id={}, operation={}, duration_seconds={:.3f}, peak_rss_mb={:.1f}',
            job_id,
            operation_name,
            perf_counter() - started_at,
            _peak_rss_mb(),
        )


def _peak_rss_mb() -> float:
    """Возвращает максимальный RSS процесса с учётом единиц Linux и macOS."""

    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    bytes_per_unit = 1 if sys.platform == 'darwin' else 1_024
    return peak_rss * bytes_per_unit / (1_024 * 1_024)

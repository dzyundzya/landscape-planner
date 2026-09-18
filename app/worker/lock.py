from types import TracebackType

from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine


class WorkerAdvisoryLock:
    """Удерживает session-level advisory lock на выделенном соединении."""

    def __init__(self, engine: AsyncEngine, lock_id: int) -> None:
        self.engine = engine
        self.lock_id = lock_id
        self._connection: AsyncConnection | None = None
        self._backend_pid: int | None = None

    async def acquire(self) -> bool:
        """Пытается получить lock без ожидания и сохраняет выделенную сессию."""

        if self._connection is not None:
            raise RuntimeError('Worker advisory lock has already been acquired')

        connection = await self.engine.connect()
        try:
            acquired = bool(
                await connection.scalar(
                    text('SELECT pg_try_advisory_lock(:lock_id)'),
                    {'lock_id': self.lock_id},
                )
            )
            if not acquired:
                await connection.close()
                return False
            backend_pid = await connection.scalar(text('SELECT pg_backend_pid()'))
            if backend_pid is None:
                await connection.close()
                return False
            await connection.commit()
        except Exception:
            await connection.close()
            raise

        self._connection = connection
        self._backend_pid = int(backend_pid)
        logger.info('Worker advisory lock получен: lock_id={}, backend_pid={}', self.lock_id, self._backend_pid)
        return True

    async def ensure_owned(self) -> None:
        """Проверяет живую исходную сессию и наличие lock без переподключения."""

        connection = self._connection
        backend_pid = self._backend_pid
        if connection is None or backend_pid is None or connection.closed:
            raise self._lost_error()

        high = (self.lock_id >> 32) & 0xFFFFFFFF
        low = self.lock_id & 0xFFFFFFFF
        try:
            row = (
                await connection.execute(
                    text(
                        """
                        SELECT pg_backend_pid() AS backend_pid,
                               EXISTS (
                                   SELECT 1
                                   FROM pg_locks
                                   WHERE locktype = 'advisory'
                                     AND pid = pg_backend_pid()
                                     AND classid::bigint = :high
                                     AND objid::bigint = :low
                                     AND objsubid = 1
                                     AND granted
                               ) AS owns_lock
                        """
                    ),
                    {'high': high, 'low': low},
                )
            ).one()
            await connection.commit()
        except SQLAlchemyError as exc:
            raise self._lost_error() from exc

        if int(row.backend_pid) != backend_pid or not row.owns_lock:
            raise self._lost_error()

    async def release(self) -> None:
        """Освобождает lock, если исходная сессия ещё доступна, и закрывает её."""

        connection = self._connection
        backend_pid = self._backend_pid
        self._connection = None
        self._backend_pid = None
        if connection is None:
            return

        try:
            if not connection.closed:
                current_pid = await connection.scalar(text('SELECT pg_backend_pid()'))
                if current_pid == backend_pid:
                    await connection.scalar(
                        text('SELECT pg_advisory_unlock(:lock_id)'),
                        {'lock_id': self.lock_id},
                    )
                    await connection.commit()
        except SQLAlchemyError:
            logger.warning('Не удалось явно освободить worker advisory lock: lock_id={}', self.lock_id)
        finally:
            await connection.close()

    async def __aenter__(self) -> 'WorkerAdvisoryLock':
        if not await self.acquire():
            raise RuntimeError('Worker advisory lock is already held')
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.release()

    def _lost_error(self) -> RuntimeError:
        return RuntimeError(f'Worker advisory lock lost: lock_id={self.lock_id}')

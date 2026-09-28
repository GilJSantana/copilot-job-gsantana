"""Controle de ritmo para chamadas a fontes externas sensíveis a bloqueio."""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from types import TracebackType


class RandomDelayThrottle:
    """Serializa requisições e garante um intervalo aleatório entre elas.

    Uso:
        async with throttle:
            await fazer_requisicao()

    O intervalo é contado a partir do *fim* da requisição anterior, então
    um scraping demorado não "consome" a pausa da próxima chamada. O jitter
    evita um padrão regular, que é facilmente detectado como bot.
    """

    def __init__(
        self,
        min_seconds: float,
        max_seconds: float,
        *,
        rng: random.Random | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if min_seconds < 0 or max_seconds < min_seconds:
            raise ValueError("exige 0 <= min_seconds <= max_seconds")
        self._min = min_seconds
        self._max = max_seconds
        self._rng = rng or random.Random()
        self._sleep = sleep
        self._clock = clock
        self._lock = asyncio.Lock()
        self._last_finished_at: float | None = None

    async def __aenter__(self) -> None:
        await self._lock.acquire()
        try:
            if self._last_finished_at is not None:
                delay = self._rng.uniform(self._min, self._max)
                remaining = delay - (self._clock() - self._last_finished_at)
                if remaining > 0:
                    await self._sleep(remaining)
        except BaseException:
            self._lock.release()
            raise

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._last_finished_at = self._clock()
        self._lock.release()

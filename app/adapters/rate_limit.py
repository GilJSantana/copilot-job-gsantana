"""Controle de ritmo para chamadas a fontes externas sensíveis a bloqueio."""

import asyncio
import math
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


class HourlyRequestBudget:
    """Janela deslizante de uma hora: quantas requisições ainda cabem no limite.

    O limite vem a cada chamada (e não no construtor) porque é configurável
    pelo painel: mudar o valor não zera a contagem das requisições recentes.
    """

    WINDOW_SECONDS = 3600.0

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._timestamps: list[float] = []

    def try_acquire(self, count: int, limit: int) -> float | None:
        """Registra `count` requisições se couberem em `limit` (0 = sem limite).

        Devolve None quando registrou ou, se não couberem, quantos segundos faltam
        para liberar espaço suficiente (nada é registrado nesse caso).
        """
        now = self._clock()
        self._timestamps = [t for t in self._timestamps if now - t < self.WINDOW_SECONDS]
        if limit and len(self._timestamps) + count > limit:
            if count > limit:
                return math.inf
            # a mais antiga que precisa sair da janela para caber `count` novas
            oldest_needed = self._timestamps[len(self._timestamps) + count - limit - 1]
            return self.WINDOW_SECONDS - (now - oldest_needed)
        self._timestamps.extend([now] * count)
        return None

import asyncio
import random

import pytest

from app.adapters.rate_limit import RandomDelayThrottle

pytestmark = pytest.mark.unit


class FakeClock:
    """Relógio controlado: `sleep` apenas avança o tempo, sem esperar de verdade."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FixedRandom(random.Random):
    """Sorteia sempre o mesmo valor, para tornar o delay determinístico."""

    def __init__(self, value: float) -> None:
        super().__init__()
        self.value = value

    def uniform(self, a: float, b: float) -> float:
        assert a <= self.value <= b
        return self.value


def make_throttle(clock: FakeClock, delay: float = 3.0) -> RandomDelayThrottle:
    return RandomDelayThrottle(2.0, 5.0, rng=FixedRandom(delay), sleep=clock.sleep, clock=clock)


async def test_first_request_does_not_wait():
    clock = FakeClock()

    async with make_throttle(clock):
        pass

    assert clock.sleeps == []


async def test_waits_the_random_delay_between_consecutive_requests():
    clock = FakeClock()
    throttle = make_throttle(clock, delay=3.0)

    for _ in range(3):
        async with throttle:
            pass

    assert clock.sleeps == [3.0, 3.0]


async def test_delay_counts_from_end_of_previous_request():
    clock = FakeClock()
    throttle = make_throttle(clock, delay=3.0)

    async with throttle:
        clock.now += 10.0  # requisição longa
    clock.now += 1.0  # tempo ocioso entre chamadas conta a favor
    async with throttle:
        pass

    assert clock.sleeps == [2.0]


async def test_skips_sleep_when_enough_time_already_passed():
    clock = FakeClock()
    throttle = make_throttle(clock, delay=3.0)

    async with throttle:
        pass
    clock.now += 60.0
    async with throttle:
        pass

    assert clock.sleeps == []


async def test_still_spaces_requests_after_a_failure():
    clock = FakeClock()
    throttle = make_throttle(clock, delay=4.0)

    with pytest.raises(RuntimeError):
        async with throttle:
            raise RuntimeError("429")
    async with throttle:
        pass

    assert clock.sleeps == [4.0]


async def test_serializes_concurrent_callers():
    throttle = RandomDelayThrottle(0.0, 0.0)
    active = 0
    max_active = 0

    async def request() -> None:
        nonlocal active, max_active
        async with throttle:
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0)
            active -= 1

    await asyncio.gather(*(request() for _ in range(5)))

    assert max_active == 1


async def test_releases_lock_when_cancelled_while_waiting():
    clock = FakeClock()
    throttle = make_throttle(clock)

    async with throttle:
        pass

    async def cancelled_sleep(seconds: float) -> None:
        raise asyncio.CancelledError

    throttle._sleep = cancelled_sleep
    with pytest.raises(asyncio.CancelledError):
        async with throttle:
            pass

    assert not throttle._lock.locked()


@pytest.mark.parametrize(("low", "high"), [(-1.0, 2.0), (5.0, 2.0)])
def test_rejects_invalid_ranges(low, high):
    with pytest.raises(ValueError):
        RandomDelayThrottle(low, high)

import time
from threading import Lock
from typing import Callable, TypeVar


T = TypeVar("T")


class TTLCache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[float, object]] = {}
        self._lock = Lock()

    def get_or_set(self, key: str, ttl_seconds: int, factory: Callable[[], T]) -> tuple[T, bool]:
        now = time.time()
        with self._lock:
            item = self._items.get(key)
            if item and item[0] > now:
                return item[1], True

        value = factory()
        with self._lock:
            self._items[key] = (now + ttl_seconds, value)
        return value, False


cache = TTLCache()

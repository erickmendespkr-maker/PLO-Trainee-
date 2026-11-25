"""Bounded exact-key memoization; concurrent requests share a single producer."""
from collections import OrderedDict
from concurrent.futures import Future
from copy import deepcopy
from threading import Lock


class SingleFlight:
    def __init__(self, capacity=512):
        if type(capacity) is not int or not 0 <= capacity <= 2048:
            raise ValueError('Invalid cache capacity')
        self.capacity = capacity
        self.cache = OrderedDict()
        self.pending = {}
        self.lock = Lock()
        self.hits = self.misses = self.shared = 0

    def get(self, key, producer):
        if not self.capacity:
            with self.lock:
                self.misses += 1
            return producer()
        with self.lock:
            if key in self.cache:
                self.hits += 1
                self.cache.move_to_end(key)
                return deepcopy(self.cache[key])
            future = self.pending.get(key)
            if future is None:
                future = Future()
                self.pending[key] = future
                self.misses += 1
                leader = True
            else:
                self.shared += 1
                leader = False
        if not leader:
            return deepcopy(future.result())
        try:
            value = producer()
            saved = deepcopy(value)
        except BaseException as exc:
            with self.lock:
                self.pending.pop(key)
                future.set_exception(exc)
            raise
        with self.lock:
            self.cache[key] = saved
            self.cache.move_to_end(key)
            while len(self.cache) > self.capacity:
                self.cache.popitem(last=False)
            self.pending.pop(key)
            future.set_result(saved)
        return value

    def stats(self):
        with self.lock:
            return {'hits': self.hits, 'misses': self.misses, 'shared_inflight': self.shared,
                    'entries': len(self.cache), 'capacity': self.capacity,
                    'key_pixel_bytes': sum(len(k[-1]) for k in self.cache)}

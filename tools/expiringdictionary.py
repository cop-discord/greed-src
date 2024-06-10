import asyncio
import datetime
import time
from typing import Any


class InvalidOperation(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class ExpiringDictionary:
    def __init__(self):
        self.dict = {}
        self.rl = {}
        self.delete = {}
        self.futures = {}

    async def do_expiration(self, key: str, expiration: int):
        await asyncio.sleep(expiration)
        if key in self.dict:
            self.dict.pop(key)

    async def do_cancel(self, key: str):
        if key in self.futures:
            try:
                self.futures[key].cancel()
            except:
                pass
            return True
        else:
            return False

    async def set(self, key: str, value: Any, expiration: int = 60):
        if key in self.futures:
            await self.do_cancel(key)
        self.dict[key] = value
        if expiration != 0:
            future = asyncio.ensure_future(self.do_expiration(key, expiration))
            self.futures[key] = future
        return 1

    async def remove(self, key: str):
        if key in self.dict:
            try:
                await self.do_cancel(key)
            except:
                pass
            self.dict.pop(key)
            return 1
        else:
            return 0

    async def get(self, key: str):
        if key in self.dict:
            return self.dict[key]
        else:
            return 0

    async def sadd(self, key: str, *value: Any, position: int = 0, expiration: int = 0):
        if key in self.futures:
            await self.do_cancel(key)
        if key in self.dict:
            if not isinstance(self.dict[key], list):
                raise InvalidOperation(
                    f"Key {key} is already in the storage and the type isnt a list"
                )
            if value in self.dict[key]:
                return 0
            self.dict[key].insert(position, value)
        else:
            self.dict[key] = []
            self.dict[key].insert(position, value)
        if expiration != 0:
            future = asyncio.ensure_future(self.do_expiration(key, expiration))
            self.futures[key] = future
        return 1

    async def sismember(self, key: str, *value: Any):
        if key not in self.dict:
            return False
        if value in self.dict[key]:
            return True
        else:
            return False

    async def smembers(self, key: str):
        if key in self.dict:
            if isinstance(self.dict[key], list):
                return set(self.dict[key])
            else:
                return None
        return None

    async def srem(self, key: str, value: Any):
        if key not in self.dict:
            return 0
        if not isinstance(self.dict[key], list):
            return 0
        if value not in self.dict[key]:
            return 0
        self.dict[key].remove(value)
        return 1

    async def keys(self):
        return list(self.dict.keys())

    async def do_delete(self, key):
        self.dict.pop(key)
        self.delete[key]["last"] = int(datetime.datetime.now().timestamp())

    def is_ratelimited(self, key: str):
        if key in self.dict:
            if self.dict[key] >= self.rl[key]:
                return True
        return False

    def time_remaining(self, key: str):
        if key in self.dict and key in self.delete:
            if not self.dict[key] >= self.rl[key]:
                return 0
            remaining = (self.delete[key]["last"] + self.delete[key]["bucket"]) - int(
                datetime.datetime.now().timestamp()
            )
            return remaining
        else:
            return 0

    async def ratelimit(self, key: str, amount: int, bucket: int = 60):
        if key not in self.dict:
            self.dict[key] = 1
            self.rl[key] = amount
            if key not in self.delete:
                self.delete[key] = {
                    "bucket": bucket,
                    "last": int(datetime.datetime.now().timestamp()),
                }
            return False
        else:
            try:
                if self.delete[key]["last"] + bucket <= int(
                    datetime.datetime.now().timestamp()
                ):
                    self.dict.pop(key)
                    self.delete[key]["last"] = int(datetime.datetime.now().timestamp())
                    self.dict[key] = 0
                self.dict[key] += 1
                if self.dict[key] >= self.rl[key]:
                    return True
                else:
                    return False
            except:
                return await self.ratelimit(key, amount, bucket)

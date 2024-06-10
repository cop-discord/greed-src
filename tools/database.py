import asyncio
import os
from types import TracebackType
from typing import Any, Iterable, Iterator, Optional, Sequence

import asyncpg
import orjson


class Record(asyncpg.Record):
    def __getattr__(self, attr: str) -> Any:
        return self[attr]


class PostgreSQL:
    _pool = asyncpg.Pool

    def __init__(self):
        self.cache = {}

    async def __aenter__(self, **kwargs):
        record_class = kwargs.pop("record_class", Record)
        self._pool = await asyncpg.create_pool(**kwargs, record_class=record_class)  # type: ignore
        return self

    async def __aexit__(self, *_):
        await self._pool.close()

    def __str__(self) -> str:
        return f"<Postgresql Cache Pool PID 69 Pool ID 420>"

    def __repr__(self) -> str:
        return f"<Postgresql Cache Pool PID 69 Pool ID 420>"

    async def delete_cache_entry(self, type: str, sql: str, *args):
        await asyncio.sleep(60)
        try:
            self.cache.pop(f"{type} {sql} {args}")
        except:
            pass

    async def add_to_cache(self, data: Any, type: str, sql: str, *args):
        self.cache[f"{type} {sql} {args}"] = data

    async def search_and_delete(self, table: str):
        for k in self.cache.keys():
            if table.lower() in k.lower():
                self.cache.pop(k)

    async def fetch(self, sql: str, *args):
        if result := self.cache.get(f"fetch {sql} {args}"):
            return result
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                data = await conn.fetch(sql, *args)
                await self.add_to_cache(data, "fetch", sql, args)
                return data

    async def fetchrow(self, sql: str, *args):
        if result := self.cache.get(f"fetchrow {sql} {args}"):
            return result
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                data = await conn.fetchrow(sql, *args)
                await self.add_to_cache(data, "fetchrow", sql, args)
                return data

    async def fetchval(self, sql: str, *args):
        if result := self.cache.get(f"fetchval {sql} {args}"):
            return result
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                data = await conn.fetchval(sql, *args)
                await self.add_to_cache(data, "fetchval", sql, args)
                return data

    async def execute(self, sql: str, *args) -> Optional[Any]:
        try:
            table = sql.lower().split("from")[1].split("where")[0]
            await self.search_and_delete(table, args)
        except:
            pass
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                return await conn.fetchval(sql, *args)

    async def executemany(self, sql: str, args: Iterable[Sequence]) -> Optional[Any]:
        if result := self.cache.get(f"{sql} {args}"):
            self.cache.pop(f"{sql} {args}")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                return await conn.executemany(sql, args)

    async def fetch_config(self, guild_id: int, key: str):
        return await self.fetchval(
            f"SELECT {key} FROM config WHERE guild_id = $1", guild_id
        )

    async def update_config(self, guild_id: int, key: str, value: str):
        await self.execute(
            f"INSERT INTO config (guild_id, {key}) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET {key} = $2",
            guild_id,
            value,
        )
        return await self.fetchrow(
            f"SELECT * FROM config WHERE guild_id = $1", guild_id
        )

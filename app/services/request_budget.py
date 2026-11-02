"""Single-replica trial budget, consumed before any provider request (including failures)."""
import asyncio
from datetime import datetime, timezone

from fastapi import HTTPException


class RequestBudget:
    def __init__(self):
        self.day = ""
        self.count = 0
        self.active = 0
        self.lock = asyncio.Lock()

    async def enter(self, daily_limit: int, concurrency: int):
        async with self.lock:
            today = datetime.now(timezone.utc).date().isoformat()
            if today != self.day:
                self.day, self.count = today, 0
            if self.count >= daily_limit:
                raise HTTPException(429, "오늘의 무료 AI 검색 한도에 도달했습니다. 일반 검색을 이용해 주세요.")
            if self.active >= concurrency:
                raise HTTPException(429, "AI 검색이 진행 중입니다. 잠시 후 다시 시도해 주세요.")
            self.count += 1
            self.active += 1

    async def leave(self):
        async with self.lock:
            self.active -= 1


provider_budget = RequestBudget()

from __future__ import annotations
import asyncio
from app.services.worker_loop import worker_forever

if __name__ == "__main__":
    asyncio.run(worker_forever())

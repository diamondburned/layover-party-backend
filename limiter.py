import os
import math
import tempfile
from typing import Callable, cast

from fastapi import HTTPException
from pyrate_limiter import (
    BucketFullException,
    LimitContextDecorator,
    RequestRate,
    Limiter,
    Duration,
    SQLiteBucket,
)

WORKING_DIR = os.path.join(tempfile.gettempdir(), "layover-party")
LIMITER_DB = os.path.join(WORKING_DIR, "limiter.db")

Rate = RequestRate
Duration = Duration
LimitedException = BucketFullException


def new(rate: RequestRate) -> Limiter:
    return Limiter(
        rate,
        bucket_class=SQLiteBucket,
        bucket_kwargs={"path": LIMITER_DB},
    )


def raise_http(full_err: BucketFullException):
    retry_after = math.ceil(cast(float, full_err.meta_info["remaining_time"]))
    raise HTTPException(
        status_code=429,
        detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
        headers={"Retry-After": str(retry_after)},
    )


async def wait(*ctx_funcs: Callable[[], LimitContextDecorator]):
    for ctx_func in ctx_funcs:
        # this library is poo and does not do async properly
        # we have to use `async with` to make it work with this junk
        async with ctx_func():
            pass

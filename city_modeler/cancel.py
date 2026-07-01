from __future__ import annotations

from typing import Callable

CancelCheck = Callable[[], None]


class GenerationCancelled(RuntimeError):
    """Raised when a user-requested job cancellation should stop generation."""


def check_cancel(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None:
        cancel_check()

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def user_dir(locate: Callable[[], str]) -> str | None:
    """Locate a per-user folder without accepting a relative or unresolved home path.

    :param locate: the platformdirs lookup to run

    :returns: the folder, or ``None`` when the home directory cannot be found

    """
    try:
        folder = locate()
    except RuntimeError:
        return None
    return folder if os.path.isabs(folder) else None


__all__ = [
    "user_dir",
]

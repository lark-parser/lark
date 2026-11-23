"""Publication and deletion of strict soft-lock claims on Windows."""

from __future__ import annotations

__lazy_modules__ = ["contextlib", "filelock._core", "filelock._filesystem", "msvcrt"]

import sys

if sys.platform == "win32":  # pragma: win32 cover
    import msvcrt
    import os
    from contextlib import nullcontext
    from errno import EWOULDBLOCK
    from typing import TYPE_CHECKING

    from filelock._core import raise_cleanup_errors
    from filelock._filesystem import (
        cancelling_oplock_wait,
        create_deletable_fd,
        mark_delete_disposition,
        oplock_wait_cancelled,
        rename_open_file,
        write_all,
    )

    if TYPE_CHECKING:
        from collections.abc import Callable
        from contextlib import AbstractContextManager

    def publish_deletable_claim(
        private_name: Callable[[], str],
        public_path: str,
        record: bytes,
        descriptors: dict[str, int],
        deadline: float | None = None,
    ) -> int:
        private_path = private_name()
        fd = create_deletable_fd(private_path)
        try:
            descriptors[public_path] = fd
            write_all(fd, record)
            with cancelling_oplock_wait(deadline):
                rename_open_file(fd, public_path)
        except BaseException as error:
            aborted = oplock_wait_cancelled(error)
            try:
                # An interrupt can arrive after the public name exists.
                if cleanup := mark_claim_for_deletion(
                    fd, private_path, None if aborted else private_name, cancel_wait=cancelling_oplock_wait(deadline)
                ):
                    raise cleanup
            except OSError as cleanup_error:
                # The reader can also block cleanup of the unpublished file.
                if not aborted or not oplock_wait_cancelled(cleanup_error):
                    raise_cleanup_errors("strict publication cleanup failed", error, cleanup_error)
            descriptors.pop(public_path, None)
            os.close(fd)
            if aborted:
                raise BlockingIOError(EWOULDBLOCK, "claim publication deferred by oplock", public_path) from error
            raise
        return fd

    def mark_claim_for_deletion(
        fd: int,
        path: str,
        private_name: Callable[[], str] | None = None,
        *,
        cancel_wait: AbstractContextManager[None] | None = None,
    ) -> OSError | None:
        sys.audit("os.remove", path, None)
        handle = msvcrt.get_osfhandle(fd)
        with cancel_wait or nullcontext():
            try:
                mark_delete_disposition(handle, published=private_name is not None)
            except OSError as error:
                # Older volumes can rename an open file even when they refuse POSIX deletion.
                if private_name is None or getattr(error, "winerror", None) not in {1, 50, 87}:
                    raise
                rename_open_file(fd, private_name())
                try:
                    mark_delete_disposition(handle, published=False)
                except OSError as cleanup_error:
                    return cleanup_error  # the rename already withdrew the public claim
        return None

    __all__ = ["mark_claim_for_deletion", "publish_deletable_claim"]
else:  # pragma: win32 no cover
    __all__ = []

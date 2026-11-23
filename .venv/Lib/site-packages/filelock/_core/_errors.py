"""Lock exceptions and rules for reporting concurrent cleanup errors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NoReturn, TypeGuard, TypeVar

from ._settings import override

if TYPE_CHECKING:
    from collections.abc import Callable


class Timeout(TimeoutError):  # ruff:ignore[error-suffix-on-exception-name]  # public exception name; renaming breaks the API
    """
    Raised when the lock could not be acquired in *timeout* seconds.

    :param lock_file: the path of the file lock
    :param holder: a description of the lock's holder, when one is recorded and this host cannot probe it
    """

    def __init__(self, lock_file: str, holder: str | None = None) -> None:
        super().__init__()
        self._lock_file = lock_file
        self._holder = holder

    @override
    def __reduce__(
        self,
    ) -> tuple[
        type[Timeout],
        tuple[str],
        dict[str, object],  # simplint: ignore[imprecise-annotation]  # pickle state is heterogeneous
    ]:
        # Older readers and subclasses accept only lock_file as a constructor argument.
        return self.__class__, (self._lock_file,), self.__dict__

    @override
    def __str__(self) -> str:  # pragma: needs hard-link
        message: Final[str] = f"The file lock '{self._lock_file}' could not be acquired."
        if self._holder is None:
            return message
        return f"{message} It is held by {self._holder}, which this host cannot probe."

    @override
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.lock_file!r})"

    @property
    def lock_file(self) -> str:
        """The path of the file lock."""
        return self._lock_file


class ReleasePendingError(TimeoutError):
    """
    The Windows strict-lock release is still running after the caller's deadline.

    :param message: identifies the lock whose release is pending
    :param wait: waits for this release and propagates the worker's error
    """

    def __init__(self, message: str, wait: Callable[[float | None], None]) -> None:  # pragma: win32 cover
        super().__init__(message)
        self._wait = wait

    @override
    def __reduce__(self) -> tuple[type[ReleasePendingError], tuple[str, Callable[[float | None], None]]]:
        return type(self), (str(self), self._wait)

    def wait(self, timeout: float | None = None) -> None:  # pragma: win32 cover
        """
        Wait for this release, including after another thread acquires the lock again.

        :param timeout: seconds to wait, or ``None`` to wait until completion
        :raises ReleasePendingError: the release is still running when the timeout expires
        """
        self._wait(timeout)


class LeaseSettingsMismatch(ValueError):  # ruff:ignore[error-suffix-on-exception-name]  # public exception name; renaming breaks the API
    """A lease contender disagrees with the published claim about how long the lease lasts."""


class SoftFileLockProtocolError(OSError):
    """
    Raised when strict soft-lock state cannot be interpreted without risking overlap.

    :param lock_file: the path of the lock
    :param claim_name: the name of the claim the state belongs to, or ``None`` when it concerns the lock as a whole
    :param reason: why the state cannot be interpreted
    """

    def __init__(self, lock_file: str, claim_name: str | None, reason: str) -> None:
        self._lock_file = lock_file
        self._claim_name = claim_name
        self._reason = reason
        super().__init__(self.__str__())

    @override
    def __str__(self) -> str:
        location = self._lock_file if self._claim_name is None else f"{self._lock_file}: claim {self._claim_name!r}"
        return f"Invalid strict soft-lock state at {location}: {self._reason}"

    @override
    def __reduce__(
        self,
    ) -> tuple[
        type[SoftFileLockProtocolError],
        tuple[str, str | None, str],
        dict[str, object],  # simplint: ignore[imprecise-annotation]  # pickle state is heterogeneous
    ]:  # pragma: needs hard-link
        return self.__class__, (self._lock_file, self._claim_name, self._reason), self.__dict__

    @property
    def lock_file(self) -> str:  # pragma: needs hard-link
        """The requested lock path."""
        return self._lock_file

    @property
    def claim_name(self) -> str | None:  # pragma: needs hard-link
        """The claim that caused the error, if scanning identified one."""
        return self._claim_name

    @property
    def reason(self) -> str:  # pragma: needs hard-link
        """The protocol validation failure."""
        return self._reason


_MarkerValue = TypeVar("_MarkerValue")


def grouped_errors(
    error: BaseException, message: str, marker: tuple[str, _MarkerValue]
) -> tuple[BaseException, ...] | None:
    if not _is_exception_group(error):
        return None
    return error.exceptions if error.message == message and getattr(error, marker[0], None) is marker[1] else None


def _is_exception_group(error: BaseException) -> TypeGuard[BaseExceptionGroup[BaseException]]:
    return isinstance(error, BaseExceptionGroup)


def raise_chained_errors(first_error: BaseException, second_error: BaseException | None = None) -> NoReturn:
    if second_error is None:
        first_context = first_error.__context__
        try:
            raise first_error  # ruff:ignore[raise-within-try]  # the handler restores caller-supplied context before propagation
        except BaseException:
            first_error.__context__ = first_context
            raise
    if (second_context := second_error.__context__) is not None and second_context is not first_error:
        _detach_exception_context(second_context, first_error)
        append_exception_context(first_error, second_context)
    first_context = first_error.__context__
    try:
        raise first_error  # ruff:ignore[raise-within-try]  # the second raise needs this error as implicit context
    except BaseException:  # ruff:ignore[blind-except]  # first_error may be a control-flow exception
        first_error.__context__ = first_context
        try:
            raise second_error  # ruff:ignore[raise-within-try]  # the handler makes the chain interpreter-independent
        except BaseException:
            second_error.__context__ = first_error
            first_error.__context__ = first_context
            raise


def _detach_exception_context(error: BaseException, target: BaseException) -> None:
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if current.__context__ is target:
            current.__context__ = None
        elif current.__context__ is not None:
            pending.append(current.__context__)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if _is_exception_group(current):
            pending.extend(current.exceptions)


def append_exception_context(error: BaseException, context: BaseException) -> None:
    if _exception_graph_contains(error, context) or _exception_graph_contains(context, error):
        return
    if error.__context__ is None:
        error.__context__ = context
        return
    tail = error
    seen: set[int] = set()
    while id(tail) not in seen:
        seen.add(id(tail))
        if (next_error := tail.__cause__ if tail.__cause__ is not None else tail.__context__) is None:
            tail.__context__ = context
            return
        tail = next_error


def _exception_graph_contains(error: BaseException, target: BaseException) -> bool:
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if current is target:
            return True
        if id(current) in seen:
            continue
        seen.add(id(current))
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
        if _is_exception_group(current):
            pending.extend(current.exceptions)
    return False


def raise_body_and_release(body_error: BaseException, release_error: BaseException) -> NoReturn:
    raise_grouped_errors("lock body and release both failed", body_error, release_error)


def raise_grouped_errors(
    message: str,
    first_error: BaseException,
    second_error: BaseException,
    *additional_errors: BaseException,
    marker: tuple[str, _MarkerValue] | None = None,
) -> NoReturn:
    errors = (first_error, second_error, *additional_errors)
    _detach_grouped_contexts(errors)
    group: Final[BaseExceptionGroup[BaseException]] = BaseExceptionGroup(message, errors)
    if marker is not None:
        setattr(group, marker[0], marker[1])
    raise group from None


def _detach_grouped_contexts(errors: tuple[BaseException, ...]) -> None:
    seen: set[int] = set()
    pending = list(errors)
    while pending:
        error = pending.pop()
        if id(error) in seen:
            continue
        seen.add(id(error))
        if (context := error.__context__) is not None and (
            context is error
            or _same_exception_tree(error, context)
            or any(context is root or _contains_exception(root, context) for root in errors)
        ):
            error.__context__ = None
        elif context is not None:
            pending.append(context)
        if error.__cause__ is not None:
            pending.append(error.__cause__)
        if _is_exception_group(error):
            pending.extend(error.exceptions)


def _same_exception_tree(first: BaseException, second: BaseException) -> bool:
    pending = [(first, second)]
    seen: set[tuple[int, int]] = set()
    while pending:
        first_error, second_error = pending.pop()
        if first_error is second_error:
            continue
        if (pair := (id(first_error), id(second_error))) in seen:
            continue
        seen.add(pair)
        if (
            type(first_error) is not type(second_error)
            or not _is_exception_group(first_error)
            or not _is_exception_group(second_error)
        ):
            return False
        if first_error.message != second_error.message or len(first_error.exceptions) != len(second_error.exceptions):
            return False
        pending.extend(zip(first_error.exceptions, second_error.exceptions, strict=True))
    return True


def _contains_exception(error: BaseException, target: BaseException | None) -> bool:
    if target is None or not _is_exception_group(error):
        return False
    pending = list(error.exceptions)
    seen: set[int] = set()
    while pending:
        child = pending.pop()
        if child is target:
            return True
        if id(child) in seen:
            continue
        seen.add(id(child))
        if _is_exception_group(child):
            pending.extend(child.exceptions)
    return False


def raise_cleanup_errors(
    message: str,
    primary_error: BaseException,
    *cleanup_errors: BaseException | None,
) -> NoReturn:
    raise_grouped_errors(
        message,
        primary_error,
        *(error for error in cleanup_errors if error is not None),
    )


def is_system_call_failure(error: BaseException) -> bool:
    # A failed system call sets errno. A bare TimeoutError raised by a signal handler is an OSError without one.
    if _is_exception_group(error):
        return all(map(is_system_call_failure, error.exceptions))
    return isinstance(error, OSError) and error.errno is not None


__all__ = [
    "LeaseSettingsMismatch",
    "ReleasePendingError",
    "SoftFileLockProtocolError",
    "Timeout",
    "append_exception_context",
    "grouped_errors",
    "is_system_call_failure",
    "raise_body_and_release",
    "raise_chained_errors",
    "raise_cleanup_errors",
    "raise_grouped_errors",
]

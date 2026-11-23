import errno
import os
import shutil
import stat

from tox import reporter


def ensure_empty_dir(path):
    if path.check():
        reporter.info("  removing {}".format(path))
        shutil.rmtree(str(path), onerror=_remove_readonly)
        path.ensure(dir=1)


def _remove_readonly(func, path, exc_info):
    """Clear the readonly bit and reattempt the removal."""
    if isinstance(exc_info[1], OSError):
        if exc_info[1].errno == errno.EACCES:
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                # when second attempt fails, ignore the problem
                # to maintain some level of backward compatibility
                pass

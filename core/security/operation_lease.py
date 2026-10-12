"""OS-owned operation locks: a process crash releases ownership automatically."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path


class OperationBusy(PermissionError):
    pass


@contextmanager
def operation_lease(database, session, task, index):
    key = hashlib.sha256(json.dumps([session,task,index], separators=(',', ':')).encode()).hexdigest()
    directory = Path(str(database) + '.locks')
    directory.mkdir(parents=True, exist_ok=True)
    handle = (directory / (key + '.lock')).open('a+b')
    acquired = False
    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'\0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            raise OperationBusy('操作仍由另一进程持有，禁止并发执行或修复；请等待或核查该进程。') from exc
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()

"""Owned storage and a process lifetime lock, including on Windows."""
import json
import os
from pathlib import Path


class ApplicationStorage:
    marker = ".educlaw-app.json"

    def __init__(self, directory, app_id):
        self.root = Path(directory).resolve()
        self._lock = None
        for parent in self.root.parents:
            if (parent / self.marker).exists():
                raise ValueError("Application data directories must not be nested.")
        marker = self.root / self.marker
        if self.root.exists() and not marker.exists() and any(self.root.iterdir()):
            raise ValueError("Refusing to adopt a nonempty directory. Choose new application storage.")
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = (self.root / ".runtime.lock").open("a+b")
        try:
            self._lock.seek(0)
            if os.name == "nt":
                import msvcrt
                if self._lock.read(1) == b"":
                    self._lock.write(b"0")
                    self._lock.flush()
                self._lock.seek(0)
                msvcrt.locking(self._lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self._lock.close()
            self._lock = None
            raise RuntimeError("Another runtime is using this application data directory.") from error
        try:
            if marker.exists():
                saved = json.loads(marker.read_text(encoding="utf-8"))
                if saved != {"app_id": app_id, "storage_version": 1}:
                    raise ValueError("Data directory belongs to a different app or storage version.")
            else:
                with marker.open("x", encoding="utf-8") as stream:
                    json.dump({"app_id": app_id, "storage_version": 1}, stream)
            self.agent_dir = self.root / "agent"
            self.business_dir = self.root / "business"
            self.agent_dir.mkdir(exist_ok=True)
            self.business_dir.mkdir(exist_ok=True)
        except BaseException:
            self.close()
            raise

    def close(self):
        if self._lock is not None:
            self._lock.close()  # OS releases byte/flock lock, even after process death.
            self._lock = None

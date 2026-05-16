"""
Watch Mode — incremental folder monitoring.

Uses watchdog OS-native events (inotify/FSEvents/ReadDirectoryChangesW).
Zero CPU when idle. NOT polling.

Flow:
  OS event → _VaultFileHandler → SHA-256 check → threading.Queue
             → asyncio drain loop (1s) → DocumentDB hash check → run_pipeline

Key properties:
  - Vault key lives in memory only — never persisted
  - Watcher pauses automatically when vault is locked (key cleared)
  - Resumes on next unlock from DB records
  - Ignores: hidden files, temp files, unsupported extensions
  - Duplicate-safe: checks DocumentDB.file_hash before queuing pipeline
"""
import asyncio
import hashlib
import logging
import os
import uuid
from pathlib import Path
from queue import Empty, Queue
from threading import Lock
from typing import NamedTuple

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md", ".html", ".htm",
    ".csv", ".json", ".epub", ".xlsx", ".xls",
    ".png", ".jpg", ".jpeg", ".webp",
}

_IGNORE_PREFIXES = (".", "~$", "._")
_IGNORE_SUFFIXES = (".tmp", ".lock", ".swp", ".swo", ".part", ".crdownload")


def _should_ignore(path: str) -> bool:
    p = Path(path)
    name = p.name
    if any(name.startswith(pfx) for pfx in _IGNORE_PREFIXES):
        return True
    if any(name.endswith(sfx) for sfx in _IGNORE_SUFFIXES):
        return True
    return p.suffix.lower() not in SUPPORTED_EXTENSIONS


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class _WatchEvent(NamedTuple):
    watcher_id: str
    vault_id: str
    file_path: str
    file_hash: str


class _VaultFileHandler(FileSystemEventHandler):
    def __init__(self, watcher_id: str, vault_id: str, event_queue: Queue,
                 last_hashes: dict, hash_lock: Lock):
        super().__init__()
        self.watcher_id = watcher_id
        self.vault_id = vault_id
        self._queue = event_queue
        self._last_hashes = last_hashes
        self._hash_lock = hash_lock

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue(str(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue(str(event.src_path))

    def _enqueue(self, path: str) -> None:
        if _should_ignore(path) or not os.path.isfile(path):
            return
        try:
            file_hash = _file_hash(path)
        except (OSError, IOError):
            return
        with self._hash_lock:
            if self._last_hashes.get(path) == file_hash:
                return
            self._last_hashes[path] = file_hash
        logger.debug(f"[Watch] Queuing: {Path(path).name} (vault {self.vault_id[:8]})")
        self._queue.put_nowait(_WatchEvent(
            watcher_id=self.watcher_id, vault_id=self.vault_id,
            file_path=path, file_hash=file_hash,
        ))


class _WatcherEntry:
    __slots__ = ("watcher_id", "vault_id", "folder_path", "watch_ref",
                 "handler", "last_hashes", "hash_lock")

    def __init__(self, watcher_id, vault_id, folder_path, watch_ref, handler):
        self.watcher_id = watcher_id
        self.vault_id = vault_id
        self.folder_path = folder_path
        self.watch_ref = watch_ref
        self.handler = handler
        self.last_hashes: dict[str, str] = {}
        self.hash_lock = Lock()


class WatcherManager:
    """Singleton. Manages all active watchers across all vaults."""

    def __init__(self):
        self._observer = Observer()
        self._observer.daemon = True
        self._event_queue: Queue[_WatchEvent] = Queue()
        self._vault_keys: dict[str, bytes] = {}
        self._keys_lock = Lock()
        self._entries: dict[str, _WatcherEntry] = {}
        self._entries_lock = Lock()
        self._task: asyncio.Task | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._observer.start()
        self._task = asyncio.create_task(self._drain_loop(), name="watcher-drain")
        self._started = True
        logger.info("[Watch] WatcherManager started.")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        try:
            self._observer.stop()
            self._observer.join(timeout=3.0)
        except Exception:
            pass
        logger.info("[Watch] WatcherManager stopped.")

    # ── Key management ────────────────────────────────────────────────────────

    def set_vault_key(self, vault_id: str, key: bytes) -> None:
        with self._keys_lock:
            self._vault_keys[vault_id] = key

    def clear_vault_key(self, vault_id: str) -> None:
        with self._keys_lock:
            self._vault_keys.pop(vault_id, None)
        logger.info(f"[Watch] Key cleared for vault {vault_id[:8]} — watchers paused.")

    def _get_key(self, vault_id: str) -> bytes | None:
        with self._keys_lock:
            return self._vault_keys.get(vault_id)

    # ── Watcher control ───────────────────────────────────────────────────────

    def add_watcher(self, vault_id: str, folder_path: str, key: bytes,
                    watcher_id: str | None = None, recursive: bool = False) -> str:
        folder = Path(folder_path).expanduser().resolve()
        if not folder.is_dir():
            raise ValueError(f"Not a directory: {folder}")

        watcher_id = watcher_id or str(uuid.uuid4())
        self.set_vault_key(vault_id, key)

        last_hashes: dict[str, str] = {}
        hash_lock = Lock()

        handler = _VaultFileHandler(
            watcher_id=watcher_id, vault_id=vault_id,
            event_queue=self._event_queue,
            last_hashes=last_hashes, hash_lock=hash_lock,
        )
        watch_ref = self._observer.schedule(handler, str(folder), recursive=recursive)

        entry = _WatcherEntry(watcher_id, vault_id, str(folder), watch_ref, handler)
        entry.last_hashes = last_hashes
        entry.hash_lock = hash_lock

        with self._entries_lock:
            self._entries[watcher_id] = entry

        logger.info(f"[Watch] Watching '{folder}' for vault {vault_id[:8]}")
        return watcher_id

    def remove_watcher(self, watcher_id: str) -> bool:
        with self._entries_lock:
            entry = self._entries.pop(watcher_id, None)
        if entry is None:
            return False
        try:
            self._observer.unschedule(entry.watch_ref)
        except Exception as e:
            logger.warning(f"[Watch] Unschedule error: {e}")
        logger.info(f"[Watch] Stopped watcher {watcher_id[:8]}")
        return True

    def remove_vault_watchers(self, vault_id: str) -> int:
        with self._entries_lock:
            ids = [wid for wid, e in self._entries.items() if e.vault_id == vault_id]
        count = sum(1 for wid in ids if self.remove_watcher(wid))
        self.clear_vault_key(vault_id)
        return count

    def get_vault_watcher_ids(self, vault_id: str) -> list[str]:
        with self._entries_lock:
            return [wid for wid, e in self._entries.items() if e.vault_id == vault_id]

    def is_watching(self, watcher_id: str) -> bool:
        with self._entries_lock:
            return watcher_id in self._entries

    async def resume_vault_watchers(self, vault_id: str, key: bytes,
                                    db_watchers: list[dict]) -> int:
        self.set_vault_key(vault_id, key)
        resumed = 0
        for row in db_watchers:
            if self.is_watching(row["id"]):
                continue
            try:
                self.add_watcher(vault_id=vault_id, folder_path=row["folder_path"],
                                 key=key, watcher_id=row["id"],
                                 recursive=row.get("recursive", False))
                resumed += 1
            except ValueError as e:
                logger.warning(f"[Watch] Cannot resume watcher {row['id'][:8]}: {e}")
        if resumed:
            logger.info(f"[Watch] Resumed {resumed} watcher(s) for vault {vault_id[:8]}")
        return resumed

    # ── Async drain loop ──────────────────────────────────────────────────────

    async def _drain_loop(self) -> None:
        logger.info("[Watch] Drain loop running.")
        while True:
            await asyncio.sleep(1.0)
            batch: list[_WatchEvent] = []
            while True:
                try:
                    batch.append(self._event_queue.get_nowait())
                except Empty:
                    break
            for event in batch:
                try:
                    await self._process_event(event)
                except Exception as e:
                    logger.exception(f"[Watch] Processing error: {e}")

    async def _process_event(self, event: _WatchEvent) -> None:
        key = self._get_key(event.vault_id)
        if key is None:
            logger.debug(f"[Watch] Skipping {Path(event.file_path).name} — vault locked")
            return
        if not os.path.isfile(event.file_path):
            return

        from database import DocumentDB, SessionLocal
        from sqlalchemy import select

        async with SessionLocal() as db:
            existing = (await db.execute(
                select(DocumentDB).where(
                    DocumentDB.vault_id == event.vault_id,
                    DocumentDB.file_hash == event.file_hash,
                )
            )).scalar_one_or_none()
            if existing:
                logger.debug(f"[Watch] {Path(event.file_path).name} already indexed — skip")
                return

        import shutil
        from config import settings
        from modules.ingestion import run_pipeline

        src = Path(event.file_path)
        ext = src.suffix.lstrip(".").lower() or "bin"
        uploads_dir = settings.DATA_DIR / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        dest = uploads_dir / f"{uuid.uuid4()}_{src.name[:80]}"

        try:
            shutil.copy2(str(src), str(dest))
        except OSError as e:
            logger.warning(f"[Watch] Copy failed for {src.name}: {e}")
            return

        logger.info(f"[Watch] Ingesting '{src.name}' → vault {event.vault_id[:8]}")

        from database import DocumentDB as _Doc, SessionLocal as _SL
        async with _SL() as db:
            doc = _Doc(vault_id=event.vault_id, filename=src.name,
                       file_type=ext, file_hash=event.file_hash, status="pending")
            db.add(doc)
            await db.commit()
            await db.refresh(doc)
            doc_id = doc.id

        asyncio.create_task(
            run_pipeline(doc_id=doc_id, vault_id=event.vault_id, key=key,
                         file_path=str(dest), filename=src.name, file_type=ext),
            name=f"watch-pipeline-{doc_id[:8]}",
        )


watcher_manager = WatcherManager()

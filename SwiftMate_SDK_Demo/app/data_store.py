import json
import threading
import os
import time
from typing import Any, Dict, List, Optional


class JSONDataStore:
    def __init__(self, path: str = None):
        self.lock = threading.Lock()
        self.path = path or os.path.join(os.path.dirname(__file__), '..', 'data_store.json')
        self.path = os.path.abspath(self.path)
        self._file_lock_path = f"{self.path}.lock"
        # Initialize file if missing
        if not os.path.exists(self.path):
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump({
                    'drugs': [],
                    'pipelines': [],
                    'identification_runs': [],
                    'metrics': []
                }, f, ensure_ascii=False, indent=2)

    def _read(self) -> Dict[str, Any]:
        with open(self.path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _write(self, data: Dict[str, Any]):
        # Acquire lightweight process lock by creating a lock file (O_EXCL)
        timeout = 5.0
        poll = 0.05
        start = time.time()
        lock_acquired = False
        while time.time() - start < timeout:
            try:
                fd = os.open(self._file_lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                lock_acquired = True
                break
            except FileExistsError:
                # check for stale lock
                try:
                    mtime = os.path.getmtime(self._file_lock_path)
                    if time.time() - mtime > 30:
                        # stale, remove
                        os.remove(self._file_lock_path)
                        continue
                except Exception:
                    pass
                time.sleep(poll)

        if not lock_acquired:
            raise RuntimeError("Could not acquire file lock for data store write")

        try:
            tmp = f"{self.path}.tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        finally:
            try:
                if os.path.exists(self._file_lock_path):
                    os.remove(self._file_lock_path)
            except Exception:
                pass

    def list_items(self, collection: str) -> List[Dict[str, Any]]:
        with self.lock:
            data = self._read()
            return data.get(collection, [])

    def get_item(self, collection: str, item_id: int) -> Optional[Dict[str, Any]]:
        with self.lock:
            data = self._read()
            for item in data.get(collection, []):
                if item.get('id') == item_id:
                    return item
            return None

    def create_item(self, collection: str, item: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            data = self._read()
            items = data.setdefault(collection, [])
            # assign id
            next_id = 1
            if items:
                next_id = max(i.get('id', 0) for i in items) + 1
            item['id'] = next_id
            items.append(item)
            self._write(data)
            return item

    def update_item(self, collection: str, item_id: int, new_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self.lock:
            data = self._read()
            items = data.get(collection, [])
            for idx, item in enumerate(items):
                if item.get('id') == item_id:
                    # keep id, update other fields
                    new_item = {**item, **new_data}
                    new_item['id'] = item_id
                    items[idx] = new_item
                    self._write(data)
                    return new_item
            return None

    def delete_item(self, collection: str, item_id: int) -> bool:
        with self.lock:
            data = self._read()
            items = data.get(collection, [])
            for idx, item in enumerate(items):
                if item.get('id') == item_id:
                    items.pop(idx)
                    self._write(data)
                    return True
            return False

    def append_to_collection(self, collection: str, item: Dict[str, Any]) -> Dict[str, Any]:
        # helper to append without overwriting ids in other collections
        return self.create_item(collection, item)


# Singleton store for app use
_store = None


def get_store(path: str = None) -> JSONDataStore:
    global _store
    if _store is None:
        _store = JSONDataStore(path=path)
    return _store

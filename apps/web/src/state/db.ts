import { MAX_RECENT_FILES, RecentFileEntry, TrackMapDef } from '@/types/telemetry';

export const DB_NAME = 'szenergy_pro_analyser_db';
export const DB_VERSION = 1;

export const STORE_KV = 'kv';
export const STORE_MAPS = 'maps';
export const STORE_RECENT_FILES = 'recent_files';

let dbPromise: Promise<IDBDatabase> | null = null;

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error('IndexedDB request failed'));
  });
}

function transactionDone(tx: IDBTransaction): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error('IndexedDB transaction failed'));
    tx.onabort = () => reject(tx.error ?? new Error('IndexedDB transaction aborted'));
  });
}

export function openDatabase(): Promise<IDBDatabase> {
  if (dbPromise) {
    return dbPromise;
  }

  dbPromise = new Promise<IDBDatabase>((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('IndexedDB is not available in this environment.'));
      return;
    }

    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_KV)) {
        db.createObjectStore(STORE_KV);
      }
      if (!db.objectStoreNames.contains(STORE_MAPS)) {
        db.createObjectStore(STORE_MAPS, { keyPath: 'slug' });
      }
      if (!db.objectStoreNames.contains(STORE_RECENT_FILES)) {
        const recentStore = db.createObjectStore(STORE_RECENT_FILES, { keyPath: 'id' });
        recentStore.createIndex('lastOpenedAt', 'lastOpenedAt', { unique: false });
      }
    };

    request.onsuccess = () => {
      const db = request.result;
      db.onversionchange = () => {
        db.close();
        dbPromise = null;
      };
      resolve(db);
    };

    request.onerror = () => {
      dbPromise = null;
      reject(request.error ?? new Error('Failed to open IndexedDB database.'));
    };

    request.onblocked = () => {
      reject(new Error('IndexedDB open request was blocked by another open tab.'));
    };
  });

  return dbPromise;
}

export async function closeDatabase(): Promise<void> {
  if (!dbPromise) {
    return;
  }
  try {
    const db = await dbPromise;
    db.close();
  } finally {
    dbPromise = null;
  }
}

export async function kvGet<T>(key: string): Promise<T | undefined> {
  const db = await openDatabase();
  const tx = db.transaction(STORE_KV, 'readonly');
  const store = tx.objectStore(STORE_KV);
  const value = await requestToPromise<T | undefined>(store.get(key));
  await transactionDone(tx);
  return value;
}

export async function kvSet<T>(key: string, value: T): Promise<void> {
  const db = await openDatabase();
  const tx = db.transaction(STORE_KV, 'readwrite');
  const store = tx.objectStore(STORE_KV);
  store.put(value, key);
  await transactionDone(tx);
}

export async function kvDelete(key: string): Promise<void> {
  const db = await openDatabase();
  const tx = db.transaction(STORE_KV, 'readwrite');
  const store = tx.objectStore(STORE_KV);
  store.delete(key);
  await transactionDone(tx);
}

export async function getAllMaps(): Promise<TrackMapDef[]> {
  const db = await openDatabase();
  const tx = db.transaction(STORE_MAPS, 'readonly');
  const store = tx.objectStore(STORE_MAPS);
  const items = await requestToPromise<TrackMapDef[]>(store.getAll());
  await transactionDone(tx);
  return (items ?? []).sort((a, b) => a.name.localeCompare(b.name));
}

export async function getMapBySlug(slug: string): Promise<TrackMapDef | undefined> {
  const db = await openDatabase();
  const tx = db.transaction(STORE_MAPS, 'readonly');
  const store = tx.objectStore(STORE_MAPS);
  const item = await requestToPromise<TrackMapDef | undefined>(store.get(slug));
  await transactionDone(tx);
  return item;
}

export async function putMap(map: TrackMapDef): Promise<void> {
  const db = await openDatabase();
  const tx = db.transaction(STORE_MAPS, 'readwrite');
  const store = tx.objectStore(STORE_MAPS);
  store.put(map);
  await transactionDone(tx);
}

export async function deleteMapBySlug(slug: string): Promise<void> {
  const db = await openDatabase();
  const tx = db.transaction(STORE_MAPS, 'readwrite');
  const store = tx.objectStore(STORE_MAPS);
  store.delete(slug);
  await transactionDone(tx);
}

export async function getRecentFiles(): Promise<RecentFileEntry[]> {
  const db = await openDatabase();
  const tx = db.transaction(STORE_RECENT_FILES, 'readonly');
  const store = tx.objectStore(STORE_RECENT_FILES);
  const all = await requestToPromise<RecentFileEntry[]>(store.getAll());
  await transactionDone(tx);
  return (all ?? [])
    .sort((a, b) => b.lastOpenedAt - a.lastOpenedAt)
    .slice(0, MAX_RECENT_FILES);
}

export async function upsertRecentFile(entry: RecentFileEntry): Promise<RecentFileEntry[]> {
  const putWithPrune = async (payload: RecentFileEntry): Promise<RecentFileEntry[]> => {
    const db = await openDatabase();
    const tx = db.transaction(STORE_RECENT_FILES, 'readwrite');
    const store = tx.objectStore(STORE_RECENT_FILES);
    store.put(payload);
    const all = await requestToPromise<RecentFileEntry[]>(store.getAll());
    const sorted = (all ?? []).sort((a, b) => b.lastOpenedAt - a.lastOpenedAt);
    if (sorted.length > MAX_RECENT_FILES) {
      for (const stale of sorted.slice(MAX_RECENT_FILES)) {
        store.delete(stale.id);
      }
    }
    await transactionDone(tx);
    return sorted.slice(0, MAX_RECENT_FILES);
  };

  try {
    return await putWithPrune(entry);
  } catch (err) {
    // Fallback if FileSystemFileHandle cannot be structured-cloned in this browser
    if (entry.handle && err instanceof DOMException && err.name === 'DataCloneError') {
      const { handle: _ignored, ...withoutHandle } = entry;
      return await putWithPrune(withoutHandle);
    }
    throw err;
  }
}

export async function deleteRecentFile(id: string): Promise<void> {
  const db = await openDatabase();
  const tx = db.transaction(STORE_RECENT_FILES, 'readwrite');
  const store = tx.objectStore(STORE_RECENT_FILES);
  store.delete(id);
  await transactionDone(tx);
}

export async function clearRecentFiles(): Promise<void> {
  const db = await openDatabase();
  const tx = db.transaction(STORE_RECENT_FILES, 'readwrite');
  const store = tx.objectStore(STORE_RECENT_FILES);
  store.clear();
  await transactionDone(tx);
}

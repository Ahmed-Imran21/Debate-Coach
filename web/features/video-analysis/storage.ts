/**
 * IndexedDB persistence for a built VisualSignalTrack, so it
 * survives a page reload between "recording stopped" and "upload
 * acknowledged" (task doc §4.11). A thin wrapper over the raw
 * API — no dependency added for this.
 */

import { INDEXEDDB_MAX_AGE_DAYS } from "./config";
import type { VisualSignalTrack } from "./types";

const DB_NAME = "debate-coach-video-analysis";
const DB_VERSION = 1;
const STORE = "signal-tracks";

interface StoredEntry {
  sessionId: string;
  track: VisualSignalTrack;
  savedAtMs: number;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "sessionId" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
  });
}

function withStore<T>(
  mode: IDBTransactionMode,
  fn: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  return openDb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const tx = db.transaction(STORE, mode);
        const request = fn(tx.objectStore(STORE));
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error ?? new Error("IndexedDB request failed"));
        tx.oncomplete = () => db.close();
      }),
  );
}

export async function saveTrack(sessionId: string, track: VisualSignalTrack): Promise<void> {
  const entry: StoredEntry = { sessionId, track, savedAtMs: Date.now() };
  await withStore("readwrite", (store) => store.put(entry));
}

export async function loadTrack(sessionId: string): Promise<VisualSignalTrack | null> {
  const entry = await withStore<StoredEntry | undefined>("readonly", (store) => store.get(sessionId));
  return entry?.track ?? null;
}

export async function deleteTrack(sessionId: string): Promise<void> {
  await withStore("readwrite", (store) => store.delete(sessionId));
}

/** Removes entries older than INDEXEDDB_MAX_AGE_DAYS. Call on app load. */
export async function cleanupOldTracks(): Promise<void> {
  const cutoffMs = Date.now() - INDEXEDDB_MAX_AGE_DAYS * 24 * 60 * 60 * 1000;
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    const request = store.openCursor();
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) return;
      const entry = cursor.value as StoredEntry;
      if (entry.savedAtMs < cutoffMs) cursor.delete();
      cursor.continue();
    };
    request.onerror = () => reject(request.error ?? new Error("IndexedDB cursor failed"));
    tx.oncomplete = () => resolve();
  });
  db.close();
}

/** Best-effort: consent/persistence is a convenience, not something to crash a recording over. */
export async function saveTrackSafely(sessionId: string, track: VisualSignalTrack): Promise<void> {
  try {
    await saveTrack(sessionId, track);
  } catch {
    // Private browsing, quota exceeded, etc. The caller still has
    // the track in memory and can try to upload it directly.
  }
}

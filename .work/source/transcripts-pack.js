/* Transcripts pack loader — single-pack client-side search system.
 *
 * Replaces the legacy 3-tier (core/extended/full) progressive index with:
 *   1. Fetch a single ~10MB brotli-compressed pack from same origin
 *   2. Cache it permanently in IndexedDB keyed by version hash
 *   3. Boot a Web Worker that does substring search on the in-memory pack
 *   4. Return search hits with snippets (before/match/after + offset)
 *
 * Public API exposed on window.TranscriptsPack:
 *   .boot()              -> Promise<{episodeCount, cached, version}>
 *   .search(query, limit?) -> Promise<{hits, took}>
 *   .pickRandom()        -> Promise<EpisodeMeta>
 *   .pickTrailer(epNum)  -> Promise<string>
 *   .onProgress(fn)      register callback for download progress events
 *   .state               read current state ('idle' | 'loading' | 'ready' | 'error')
 *
 * Ported from gooaye-player/src/{boot,store,searchClient}.ts.
 */

(function () {
  'use strict';

  const DB_NAME = 'gooaye-transcripts';
  const DB_VERSION = 1;
  const STORE_PACKS = 'packs';

  // ──────────────────────────────────────────────────────────────────────────
  // IndexedDB cache
  // ──────────────────────────────────────────────────────────────────────────

  function openDb() {
    return new Promise(function (resolve, reject) {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onerror = function () { reject(req.error); };
      req.onsuccess = function () { resolve(req.result); };
      req.onupgradeneeded = function () {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE_PACKS)) {
          db.createObjectStore(STORE_PACKS, { keyPath: 'version' });
        }
      };
    });
  }

  function getStoredPack(version) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        const tx = db.transaction(STORE_PACKS, 'readonly');
        const store = tx.objectStore(STORE_PACKS);
        const req = store.get(version);
        req.onerror = function () { reject(req.error); };
        req.onsuccess = function () {
          db.close();
          resolve(req.result || null);
        };
      });
    });
  }

  function putStoredPack(pack) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        const tx = db.transaction(STORE_PACKS, 'readwrite');
        const store = tx.objectStore(STORE_PACKS);
        store.put(pack);
        // drop other versions
        const cur = store.openCursor();
        cur.onsuccess = function () {
          const c = cur.result;
          if (!c) return;
          if (c.key !== pack.version) c.delete();
          c.continue();
        };
        cur.onerror = function () { reject(cur.error); };
        tx.oncomplete = function () { db.close(); resolve(); };
        tx.onerror = function () { reject(tx.error); };
      });
    });
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Network fetch
  // ──────────────────────────────────────────────────────────────────────────

  function fetchManifest() {
    return fetch('/pack_manifest.json', { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error('manifest fetch failed: ' + r.status);
      return r.json();
    });
  }

  function fetchTranscriptPack(onProgress) {
    // Fetch the precompressed brotli asset directly. Vercel sends
    // Content-Encoding: br on this URL (configured in vercel.json), so the
    // browser transparently decompresses. We never download 36 MB of raw JSON.
    //
    // Local dev (python3 -m http.server) doesn't add Content-Encoding: br,
    // so the browser would receive raw brotli bytes and JSON.parse would
    // throw. On localhost we fetch the uncompressed JSON instead.
    const isLocal = /^(localhost|127\.0\.0\.1|::1|\[::1\])$/i.test(location.hostname);
    const packUrl = isLocal ? '/transcripts.json' : '/transcripts.json.br';
    return fetch(packUrl).then(function (res) {
      if (!res.ok) throw new Error('transcripts fetch failed: ' + res.status);
      const total = Number(res.headers.get('Content-Length')) || 0;
      const reader = res.body && res.body.getReader && res.body.getReader();
      if (!reader) {
        // Fallback for browsers without ReadableStream
        return res.json();
      }
      const chunks = [];
      let received = 0;
      function pump() {
        return reader.read().then(function (chunk) {
          if (chunk.done) {
            // assemble
            const merged = new Uint8Array(received);
            let offset = 0;
            for (let i = 0; i < chunks.length; i++) {
              merged.set(chunks[i], offset);
              offset += chunks[i].byteLength;
            }
            const text = new TextDecoder('utf-8').decode(merged);
            return JSON.parse(text);
          }
          chunks.push(chunk.value);
          received += chunk.value.byteLength;
          if (onProgress) {
            onProgress({
              received: received,
              total: total,
              ratio: total ? received / total : 0,
            });
          }
          return pump();
        });
      }
      return pump();
    });
  }

  function getConnectionHint() {
    const c = (typeof navigator !== 'undefined') ? navigator.connection : null;
    if (!c) return 'unknown';
    if (c.saveData) return 'save-data';
    const t = c.effectiveType;
    if (t === '4g') return 'cellular-fast';
    if (t === '3g' || t === '2g' || t === 'slow-2g') return 'cellular-slow';
    return 'unknown';
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Worker comms
  // ──────────────────────────────────────────────────────────────────────────

  let worker = null;
  let nextId = 1;
  const pending = new Map();

  function ensureWorker() {
    if (worker) return worker;
    worker = new Worker('/search-worker.js');
    worker.addEventListener('message', function (e) {
      const data = e.data || {};
      const cb = pending.get(data.id);
      if (cb) {
        pending.delete(data.id);
        cb(data);
      }
    });
    worker.addEventListener('error', function (e) {
      console.error('[search-worker] error:', e.message || e);
    });
    return worker;
  }

  function call(req) {
    const w = ensureWorker();
    const id = nextId++;
    return new Promise(function (resolve, reject) {
      pending.set(id, function (msg) {
        if (msg.type === 'error') reject(new Error(msg.message));
        else resolve(msg);
      });
      const payload = Object.assign({}, req, { id: id });
      w.postMessage(payload);
    });
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Boot orchestration
  // ──────────────────────────────────────────────────────────────────────────

  let state = 'idle'; // idle | loading-meta | awaiting-consent | loading-pack | ready | error
  let stateInfo = {};
  const progressListeners = [];
  let bootPromise = null;

  function notifyProgress(evt) {
    for (let i = 0; i < progressListeners.length; i++) {
      try { progressListeners[i](evt); } catch (e) { /* ignore */ }
    }
  }

  function setState(name, info) {
    state = name;
    stateInfo = info || {};
    notifyProgress({ type: 'state', state: name, info: stateInfo });
  }

  function boot(opts) {
    if (bootPromise) return bootPromise;
    opts = opts || {};

    bootPromise = (function () {
      setState('loading-meta');
      return fetchManifest().then(function (manifest) {
        notifyProgress({ type: 'manifest', manifest: manifest });

        return getStoredPack(manifest.version).then(function (stored) {
          if (stored) {
            setState('initializing-worker');
            return call({ type: 'init', episodes: stored.episodes }).then(function () {
              setState('ready', { version: manifest.version, cached: true, episodeCount: stored.episodes.length });
              return { version: manifest.version, cached: true, episodeCount: stored.episodes.length };
            });
          }

          // Need to fetch the pack
          const conn = getConnectionHint();
          if ((conn === 'cellular-slow' || conn === 'save-data') && !opts.skipConsent) {
            setState('awaiting-consent', {
              manifest: manifest,
              reason: conn === 'save-data' ? 'data-saver' : 'slow-cellular',
              estimatedBytes: manifest.transcripts.brotli_bytes || manifest.transcripts.gzip_bytes,
            });
            // resolve the boot promise with a "waiting" state; caller can prompt user
            // and then call boot({ skipConsent: true }) again
            bootPromise = null; // allow re-invocation
            return { state: 'awaiting-consent' };
          }

          return downloadAndStore(manifest);
        });
      }).catch(function (err) {
        setState('error', { error: err && err.message || String(err) });
        bootPromise = null; // allow retry
        throw err;
      });
    })();

    return bootPromise;
  }

  function downloadAndStore(manifest) {
    setState('loading-pack', {
      total: manifest.transcripts.brotli_bytes || manifest.transcripts.gzip_bytes || manifest.transcripts.bytes,
    });
    return fetchTranscriptPack(function (progress) {
      notifyProgress({ type: 'progress', progress: progress });
    }).then(function (episodes) {
      setState('caching-pack');
      return putStoredPack({
        version: manifest.version,
        fetched_at: Date.now(),
        episodes: episodes,
      }).then(function () {
        setState('initializing-worker');
        return call({ type: 'init', episodes: episodes }).then(function () {
          setState('ready', { version: manifest.version, cached: false, episodeCount: episodes.length });
          return { version: manifest.version, cached: false, episodeCount: episodes.length };
        });
      });
    });
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Public API
  // ──────────────────────────────────────────────────────────────────────────

  function search(query, limit) {
    return call({ type: 'search', query: query, limit: limit || 50 }).then(function (msg) {
      return { hits: msg.hits, took: msg.took };
    });
  }

  function pickRandom() {
    return call({ type: 'random' }).then(function (msg) { return msg.episode; });
  }

  function pickTrailer(epNum) {
    return call({ type: 'randomTrailer', episodeNumber: epNum }).then(function (msg) { return msg.trailer; });
  }

  function onProgress(fn) {
    progressListeners.push(fn);
    // also fire current state immediately so subscribers don't miss the boat
    fn({ type: 'state', state: state, info: stateInfo });
    return function unsubscribe() {
      const idx = progressListeners.indexOf(fn);
      if (idx >= 0) progressListeners.splice(idx, 1);
    };
  }

  window.TranscriptsPack = {
    boot: boot,
    search: search,
    pickRandom: pickRandom,
    pickTrailer: pickTrailer,
    onProgress: onProgress,
    get state() { return state; },
    get stateInfo() { return stateInfo; },
  };
})();

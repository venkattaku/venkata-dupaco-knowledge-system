"""Dense passage vectors (DeepInfra embeddings API + numpy). Optional: any failure turns it off and search falls back to
FTS5 only, so the solution never depends on it. Vectors are built once per distinct passage during ingest and cached on
disk (.emb_cache.pkl); the question vector is computed in a background thread while the router LLM is thinking."""
import concurrent.futures as cf
import hashlib
import json
import os
import pickle
import random
import time
import urllib.error
import urllib.request

from . import trace
from .llm import BASE, _ssl

try:
    import numpy as np
except Exception:                                   # numpy missing: vectors off
    np = None

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "     # bge retrieval convention


class Vectors:
    def __init__(self, key):
        self.key = key
        self.model = os.environ.get("EMBED_MODEL", "BAAI/bge-base-en-v1.5")
        self.qprefix = os.environ.get("EMBED_QUERY_PREFIX", QUERY_PREFIX)
        self.batch = int(os.environ.get("EMBED_BATCH", "64"))
        self.workers = int(os.environ.get("EMBED_WORKERS", "8"))
        self.budget_s = float(os.environ.get("EMBED_BUDGET_S", "900"))       # ingest limit is 30 min; stay far under
        self.cache_path = os.environ.get("EMBED_CACHE", ".emb_cache.pkl")
        self.ctx = _ssl()
        self.fmt = True
        self.probed = False
        self.ok = True
        self.ids, self._chunks, self._mat = [], [], None
        self.cache = {}
        try:
            if os.path.exists(self.cache_path):
                with open(self.cache_path, "rb") as f:
                    self.cache = pickle.load(f)
        except Exception:
            self.cache = {}
        self._qcache = {}

    @classmethod
    def from_env(cls):
        k = os.environ.get("DEEPINFRA_API_KEY")
        if not k or np is None or os.environ.get("EMBED_MODEL", "").lower() == "off":
            return None
        return cls(k)

    # ------------------------------------------------------------ api
    def _post(self, inputs):
        req_body = {"model": self.model, "input": inputs}
        if self.fmt:
            req_body["encoding_format"] = "float"
        body = json.dumps(req_body).encode()
        req = urllib.request.Request(BASE + "/embeddings", data=body, method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.key,
                                              "User-Agent": "dupaco-knowledge/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30, context=self.ctx) as r:
                d = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError("HTTP %s %s" % (e.code, e.read()[:200].decode("utf-8", "ignore")))
        data = sorted(d["data"], key=lambda x: x.get("index", 0))
        if len(data) != len(inputs):
            raise ValueError("embedding count mismatch")
        return [np.asarray(x["embedding"], dtype=np.float32) for x in data]

    def _embed_batch(self, inputs, deadline):
        """Embed a batch; a 4xx (bad input) splits the batch until the offending passage is isolated and skipped (None)."""
        try:
            return self._embed_batch_raw(inputs, deadline)
        except RuntimeError as e:
            if "HTTP 4" not in str(e) or "HTTP 429" in str(e):
                raise
            if len(inputs) == 1:
                trace.log("embed_skip", chars=len(inputs[0]), error=str(e)[:200])
                return [None]
            h = len(inputs) // 2
            return self._embed_batch(inputs[:h], deadline) + self._embed_batch(inputs[h:], deadline)

    def _embed_batch_raw(self, inputs, deadline):
        err = None
        for a in range(4):
            if time.time() > deadline:
                break
            try:
                return self._post(inputs)
            except Exception as e:
                err = e
                if "HTTP 4" in str(e) and "HTTP 429" not in str(e):      # bad input: retrying cannot help
                    break
                time.sleep(min(8, 0.5 * 2 ** a) * (0.5 + random.random()))
        raise RuntimeError("embeddings failed: %r" % (err,))

    @staticmethod
    def _norm(v):
        n = float(np.linalg.norm(v))
        return (v / n).astype(np.float32) if n else v.astype(np.float32)

    CANDIDATES = ["BAAI/bge-base-en-v1.5", "BAAI/bge-large-en-v1.5", "BAAI/bge-m3", "Qwen/Qwen3-Embedding-0.6B",
                  "sentence-transformers/all-MiniLM-L6-v2"]

    def _prefix_for(self, model):
        if os.environ.get("EMBED_QUERY_PREFIX") is not None:
            return os.environ["EMBED_QUERY_PREFIX"]
        if model.startswith("BAAI/bge-") and "m3" not in model:
            return QUERY_PREFIX
        if "Qwen3-Embedding" in model:
            return "Instruct: Given a question, retrieve the passages that answer it\nQuery: "
        return ""

    def _probe(self):
        """Find a working (model, request format) once; every failure is logged with the API's error text."""
        self.probed = True
        first = os.environ.get("EMBED_MODEL")
        models = ([first] if first else []) + [m for m in self.CANDIDATES if m != first]
        for m in models:
            for fmt in (True, False):
                self.model, self.fmt = m, fmt
                try:
                    self._post(["probe"])
                    self.qprefix = self._prefix_for(m)
                    trace.log("embed_model", model=m, encoding_format=fmt)
                    return True
                except Exception as e:
                    trace.log("embed_probe_failed", model=m, encoding_format=fmt, error=repr(e)[:300])
        return False

    # ------------------------------------------------------------ passages (ingest)
    def add(self, ids, texts):
        """Embed new passages (cache first). On any failure vectors are switched off for the whole run."""
        if not self.ok or not ids:
            return
        t0 = time.time()
        if not self.probed and not self._probe():
            self.ok = False
            trace.log("embed_off", error="no embedding model worked")
            return
        keys = [hashlib.sha1((self.model + "|" + t).encode("utf-8", "ignore")).hexdigest() for t in texts]
        texts = [(t.strip() or "-")[:800] for t in texts]
        keys = [hashlib.sha1((self.model + "|" + t).encode("utf-8", "ignore")).hexdigest() for t in texts]
        todo = [i for i, k in enumerate(keys) if k not in self.cache]
        try:
            if todo:
                deadline = t0 + self.budget_s
                groups = [todo[i:i + self.batch] for i in range(0, len(todo), self.batch)]
                with cf.ThreadPoolExecutor(max_workers=self.workers) as ex:
                    futs = [(g, ex.submit(self._embed_batch, [texts[i] for i in g], deadline)) for g in groups]
                    try:
                        for g, f in futs:
                            for i, v in zip(g, f.result()):
                                self.cache[keys[i]] = self._norm(v).astype(np.float16) if v is not None else None
                    finally:                               # keep what was paid for, even if a later batch fails
                        try:
                            with open(self.cache_path, "wb") as fh:
                                pickle.dump(self.cache, fh, protocol=4)
                        except Exception:
                            pass
            for sid, k in zip(ids, keys):
                if self.cache.get(k) is not None:
                    self.ids.append(sid)
                    self._chunks.append(self.cache[k])
            self._mat = None
            trace.log("embed", n=len(ids), new=len(todo), model=self.model, seconds=round(time.time() - t0, 1))
        except Exception as e:
            self.ok = False
            self.ids, self._chunks, self._mat = [], [], None
            trace.log("embed_off", error=repr(e))

    # ------------------------------------------------------------ query
    def query_vec(self, text):
        if not self.ok or not text:
            return None
        if text in self._qcache:
            return self._qcache[text]
        try:
            v = self._norm(self._embed_batch([self.qprefix + text], time.time() + 12)[0])
        except Exception as e:
            trace.log("embed_query_error", error=repr(e))
            return None
        self._qcache[text] = v
        return v

    def top(self, qv, k=60):
        """[(passage id, cosine)] best first."""
        if not self.ok or qv is None or not self.ids:
            return []
        if self._mat is None:
            self._mat = np.stack(self._chunks).astype(np.float32)
        sc = self._mat @ qv
        k = min(k, len(sc))
        idx = np.argpartition(-sc, k - 1)[:k]
        idx = idx[np.argsort(-sc[idx])]
        return [(self.ids[i], float(sc[i])) for i in idx]

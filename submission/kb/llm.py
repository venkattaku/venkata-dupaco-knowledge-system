"""Minimal DeepInfra client (OpenAI-compatible chat completions with tool calling).

Key from the DEEPINFRA_API_KEY environment variable only. Follows DeepInfra's tool-calling guidance: tool_choice "auto",
no system message (instructions go in the user message), temperature 0. Disk cache, call budget, retries with backoff."""
import concurrent.futures as cf
import hashlib
import json
import os
import random
import ssl
import time
import urllib.error
import urllib.request

BASE = os.environ.get("DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai")
PREFERRED = ["deepseek-ai/DeepSeek-V4-Flash-0731", "Qwen/Qwen3-235B-A22B-Instruct-2507",
             "meta-llama/Llama-3.3-70B-Instruct-Turbo"]


def _ssl():
    files = []
    try:
        import certifi
        files.append(certifi.where())
    except Exception:
        pass
    files += [os.environ.get("SSL_CERT_FILE", ""), "/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt",
              "/opt/homebrew/etc/ca-certificates/cert.pem"]
    for f in files:
        if f and os.path.exists(f):
            try:
                return ssl.create_default_context(cafile=f)
            except Exception:
                pass
    return ssl.create_default_context()


class LLM:
    def __init__(self, key, model=None, timeout=15.0):
        self.key, self.timeout, self.ctx = key, timeout, _ssl()
        self.model = model or os.environ.get("DEEPINFRA_MODEL", PREFERRED[0])
        self.budget = int(os.environ.get("LLM_MAX_CALLS", "600"))
        self.retries = int(os.environ.get("LLM_RETRIES", "5"))
        self.hedge = float(os.environ.get("LLM_HEDGE_S", "3.5"))      # send a duplicate request if no reply by then
        self.cache_path = os.environ.get("LLM_CACHE", ".llm_cache.json")
        try:
            self.cache = json.load(open(self.cache_path, encoding="utf-8")) if os.path.exists(self.cache_path) else {}
        except Exception:
            self.cache = {}
        self.fail_streak, self.dead = 0, False
        self.last = {"cached": False, "ms": None, "model": self.model, "errors": [], "waited": 0.0, "attempts": 0}

    @classmethod
    def from_env(cls):
        k = os.environ.get("DEEPINFRA_API_KEY")
        return cls(k) if k else None

    def _post(self, path, body=None):
        req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None,
                                     method="POST" if body else "GET",
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.key,
                                              "User-Agent": "dupaco-knowledge/1.0"})
        with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
            return json.loads(r.read().decode())

    def _post_hedged(self, path, body):
        """Tail-latency guard: if the first request is still pending after `hedge` seconds, send an identical second
        one and take whichever succeeds first (the provider's latency is spiky: usually 1-2 s, sometimes 10 s)."""
        ex = cf.ThreadPoolExecutor(max_workers=2)
        try:
            futs = [ex.submit(self._post, path, body)]
            done, _ = cf.wait(futs, timeout=self.hedge)
            if not done:
                futs.append(ex.submit(self._post, path, body))
                self.last["hedged"] = True
            pending, err = set(futs), None
            while pending:
                done, pending = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
                for f in done:
                    try:
                        return f.result()
                    except Exception as e:
                        err = e
            raise err
        finally:
            ex.shutdown(wait=False)

    def available_models(self):
        return [m["id"] for m in self._post("/models")["data"]]

    def _pick_model(self):
        avail = self.available_models()
        for m in PREFERRED:
            if m in avail and m != self.model:
                self.model = m
                return True
        return False

    @staticmethod
    def _wait(e, attempt):
        h = e.headers.get("retry-after") if e is not None else None
        v = float(h) if h else min(2 ** attempt, 16)
        return min(v, 30) + random.uniform(0.1, 0.6)

    def tool_call(self, instructions, user, tools, force=None):
        """Returns [(tool_name, args_dict)] or None. `force` names the function the model is asked to call; if it
        answers in plain text instead, that text is returned as that function's `text` argument."""
        key = hashlib.sha1(json.dumps([self.model, instructions, user, [t["function"]["name"] for t in tools], force],
                                      sort_keys=True).encode()).hexdigest()
        self.last = {"cached": False, "ms": None, "model": self.model, "errors": [], "waited": 0.0, "attempts": 0}
        if key in self.cache:
            self.last["cached"] = True
            return [tuple(c) for c in self.cache[key]]
        if self.dead or self.budget <= 0:
            return None
        body = {"model": self.model, "temperature": 0, "max_tokens": 600, "tools": tools, "tool_choice": "auto",
                "messages": [{"role": "user", "content": instructions + "\n\n" + user}]}   # no system message (DeepInfra tip)
        t_start = time.time()
        for attempt in range(self.retries + 1):
            self.last["attempts"] += 1
            self.budget -= 1
            e = None
            try:
                msg = self._post_hedged("/chat/completions", body)["choices"][0]["message"]
                calls = [(c["function"]["name"], json.loads(c["function"]["arguments"] or "{}"))
                         for c in msg.get("tool_calls") or []]
                if not calls and force and (msg.get("content") or "").strip():
                    calls = [(force, {"text": msg["content"].strip(), "confident": True, "rows": []})]
                if not calls:
                    self.last["errors"].append("model returned no tool call")
                    break
                self.cache[key] = calls
                try:
                    json.dump(self.cache, open(self.cache_path, "w", encoding="utf-8"))
                except Exception:
                    pass
                self.fail_streak = 0
                self.last.update(ms=int((time.time() - t_start) * 1000), model=self.model)
                return calls
            except urllib.error.HTTPError as err:
                e, text = err, err.read().decode()[:400]
                self.last["errors"].append("HTTP %s (try %d): %s" % (err.code, attempt + 1, text[:160]))
                if err.code in (400, 404) and "model" in text.lower() and attempt < 2:
                    try:
                        if self._pick_model():
                            body["model"] = self.model
                            continue
                    except Exception:
                        pass
                    break
                if err.code not in (408, 409, 429) and err.code < 500:
                    break                                    # other 4xx: retrying will not help (bad key, bad request)
            except Exception as err:                         # timeout, connection reset, DNS, bad JSON ...
                self.last["errors"].append("%s (try %d): %s" % (type(err).__name__, attempt + 1, err))
            if attempt < self.retries:
                w = self._wait(e, attempt)
                self.last["waited"] += w
                time.sleep(w)
        self.fail_streak += 1
        if self.fail_streak >= 5:
            self.dead = True                                 # stop paying latency when the API is clearly unreachable
        return None

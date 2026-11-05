"""Intent router backed by Groq function calling (optional).

The model never writes SQL or answers. It only chooses one intent from the verified-query catalog
(plus an optional product family), via a forced tool call. No key, no network, a timeout or an
unknown intent all return None and the engine falls back to its rule-based router.

The API key is read from the GROQ_API_KEY environment variable only.
"""
import json
import os
import urllib.request

URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1") + "/chat/completions"
FAMILIES = ["mortgage", "home_improvement", "auto", "personal_loan", "cert", "checking", "savings", "card", "none"]


class GroqRouter:
    def __init__(self, catalog, api_key, model=None, timeout=1.8):
        self.cat, self.key = catalog, api_key
        self.model = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.timeout = timeout
        self.cache = {}
        self.failures = 0

    @classmethod
    def from_env(cls, catalog):
        key = os.environ.get("GROQ_API_KEY")
        return cls(catalog, key) if key else None

    def _tool(self):
        return {"type": "function", "function": {
            "name": "route_question",
            "description": "Pick the verified-query intent that answers the member's question.",
            "parameters": {"type": "object", "properties": {
                "intent": {"type": "string", "enum": self.cat.intent_names()},
                "family": {"type": "string", "enum": FAMILIES,
                           "description": "Product family for rate_lookup / credit_cards, else none."},
                "branch": {"type": "string", "description": "Branch/place named in the question, else empty."}},
                "required": ["intent"]}}}

    def _system(self):
        lines = ["You route questions from members of Dupaco Credit Union to one intent. Call route_question.",
                 "Intents:"]
        for i in self.cat.intents:
            lines.append("- %s: %s e.g. %s" % (i["name"], i["description"], " | ".join(i["examples"][:2])))
        lines.append("Use general_fact when no other intent fits.")
        return "\n".join(lines)

    def route(self, question):
        k = " ".join(question.lower().split())
        if k in self.cache:
            return self.cache[k]
        if self.failures >= 3:                       # stop paying latency once the API is clearly unreachable
            return None
        body = {"model": self.model, "temperature": 0, "max_tokens": 120,
                "messages": [{"role": "system", "content": self._system()}, {"role": "user", "content": question}],
                "tools": [self._tool()], "tool_choice": {"type": "function", "function": {"name": "route_question"}}}
        req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + self.key,
            "User-Agent": "dupaco-knowledge/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode())
            args = json.loads(data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])
            if args.get("intent") not in self.cat.intent_names():
                raise ValueError("unknown intent")
            self.failures = 0
            self.cache[k] = args
            return args
        except Exception:
            self.failures += 1
            return None

#!/usr/bin/env python3
"""One real round trip with full error output. Usage: DEEPINFRA_API_KEY=... python3 tools/check_llm.py ["question"]"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "submission"))
from kb.catalog import Catalog  # noqa: E402
from kb.llm import LLM  # noqa: E402

os.environ.setdefault("LLM_CACHE", "")
g = LLM.from_env()
if not g:
    sys.exit("export DEEPINFRA_API_KEY first (in the same terminal)")
try:
    ids = g.available_models()
    print("%d models; configured model %s available: %s" % (len(ids), g.model, g.model in ids))
except Exception as e:
    print("could not list models:", e)
for q in sys.argv[1:] or ["What is the APR on a 36-month personal loan?", "What is Dupaco's routing number?"]:
    t = time.time()
    out = g.tool_call("Pick the best tool for the question.", q, Catalog().schemas())
    print(q, "->", out, "(%.2fs, model %s)" % (time.time() - t, g.model), g.last["errors"] or "")

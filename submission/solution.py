"""
Dupaco knowledge system: ingest snapshots into SQLite, answer with verified queries.

    build() -> KnowledgeSystem   (ingest / answer / conflicts)

An LLM (DeepInfra, DEEPINFRA_API_KEY) chooses the verified query and writes the answer from its rows; see NOTES.md.
"""
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
sys.path.insert(0, str(_here))
for _d in _here.parents:
    if (_d / "harness" / "contract.py").exists():
        sys.path.insert(0, str(_d / "harness"))
        break

from contract import Answer, Snapshot  # noqa: E402
from kb.engine import Engine  # noqa: E402
from kb.store import Store  # noqa: E402


class DupacoKnowledge:
    def __init__(self):
        self.store = Store()
        self.engine = Engine(self.store)

    def ingest(self, snapshot: Snapshot) -> None:
        self.store.ingest(snapshot)
        self.engine.warm()

    def answer(self, question, as_of=None) -> Answer:
        return self.engine.answer(question, as_of)

    def conflicts(self):
        return self.engine.conflicts()


def build():
    return DupacoKnowledge()

"""RunRepository: abstracts persistence of runs, candidates, and decisions.

`InMemoryRunRepository` is a process-local implementation suitable for local
development and tests. A future `FirestoreRunRepository` should implement
the same interface backed by Firestore collections (see
`Settings.firestore_database` in app/core/config.py) — nothing outside this
module should need to change when that lands.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from app.models.candidate import CandidateConfiguration
from app.models.decision import DecisionRecord
from app.models.run import OptimizationRun


class RunRepositoryError(Exception):
    """Raised for persistence failures, including "not found"."""


class RunRepository(ABC):
    @abstractmethod
    def create_run(self, run: OptimizationRun) -> OptimizationRun: ...

    @abstractmethod
    def update_run(self, run: OptimizationRun) -> OptimizationRun: ...

    @abstractmethod
    def get_run(self, run_id: str) -> OptimizationRun: ...

    @abstractmethod
    def list_runs(self) -> list[OptimizationRun]: ...

    @abstractmethod
    def save_candidate(self, candidate: CandidateConfiguration) -> CandidateConfiguration: ...

    @abstractmethod
    def list_candidates(self, run_id: str) -> list[CandidateConfiguration]: ...

    @abstractmethod
    def save_decision(self, decision: DecisionRecord) -> DecisionRecord: ...

    @abstractmethod
    def list_decisions(self, run_id: str) -> list[DecisionRecord]: ...


class InMemoryRunRepository(RunRepository):
    """Dict-backed RunRepository. Not persisted across process restarts."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, OptimizationRun] = {}
        self._candidates: dict[str, list[CandidateConfiguration]] = {}
        self._decisions: dict[str, list[DecisionRecord]] = {}

    def create_run(self, run: OptimizationRun) -> OptimizationRun:
        with self._lock:
            if run.id in self._runs:
                raise RunRepositoryError(f"Run already exists: {run.id}")
            self._runs[run.id] = run
            self._candidates.setdefault(run.id, [])
            self._decisions.setdefault(run.id, [])
            return run

    def update_run(self, run: OptimizationRun) -> OptimizationRun:
        with self._lock:
            if run.id not in self._runs:
                raise RunRepositoryError(f"No such run: {run.id}")
            run.updated_at = datetime.now(timezone.utc)
            self._runs[run.id] = run
            return run

    def get_run(self, run_id: str) -> OptimizationRun:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError as exc:
                raise RunRepositoryError(f"No such run: {run_id}") from exc

    def list_runs(self) -> list[OptimizationRun]:
        with self._lock:
            return list(self._runs.values())

    def save_candidate(self, candidate: CandidateConfiguration) -> CandidateConfiguration:
        with self._lock:
            if candidate.run_id not in self._runs:
                raise RunRepositoryError(f"No such run: {candidate.run_id}")
            bucket = self._candidates.setdefault(candidate.run_id, [])
            for i, existing in enumerate(bucket):
                if existing.id == candidate.id:
                    bucket[i] = candidate
                    return candidate
            bucket.append(candidate)
            return candidate

    def list_candidates(self, run_id: str) -> list[CandidateConfiguration]:
        with self._lock:
            return list(self._candidates.get(run_id, []))

    def save_decision(self, decision: DecisionRecord) -> DecisionRecord:
        with self._lock:
            if decision.run_id not in self._runs:
                raise RunRepositoryError(f"No such run: {decision.run_id}")
            self._decisions.setdefault(decision.run_id, []).append(decision)
            return decision

    def list_decisions(self, run_id: str) -> list[DecisionRecord]:
        with self._lock:
            return list(self._decisions.get(run_id, []))


__all__ = ["RunRepository", "InMemoryRunRepository", "RunRepositoryError"]

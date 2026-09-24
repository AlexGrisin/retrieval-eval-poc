"""Durable, comparable records for a live deployed-skill evaluation run."""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import urlopen


MANIFEST_SCHEMA_VERSION = 1


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _command_output(command: list[str], *, cwd: Path | None = None) -> str | None:
    try:
        completed = subprocess.run(
            command, cwd=cwd, text=True, capture_output=True, check=False, timeout=10
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def git_metadata(path: Path) -> dict[str, Any]:
    """Return an explicit revision record, including uncommitted local changes."""
    root = _command_output(["git", "-C", str(path), "rev-parse", "--show-toplevel"])
    if root is None:
        return {"path": str(path), "available": False}
    root_path = Path(root)
    return {
        "path": str(root_path),
        "available": True,
        "commit": _command_output(["git", "-C", str(root_path), "rev-parse", "HEAD"]),
        "dirty": bool(_command_output(["git", "-C", str(root_path), "status", "--porcelain"])),
    }


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(path: Path) -> str:
    """Hash a plugin checkout's file names and bytes, excluding local caches."""
    digest = hashlib.sha256()
    files = sorted(
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file() and not {".git", "__pycache__"}.intersection(candidate.parts)
    )
    for candidate in files:
        digest.update(candidate.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(candidate.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def server_snapshot(server_base_url: str, domains: list[str]) -> dict[str, Any]:
    """Identify the live server and the ingested data it will answer from.

    The source registry exposes each domain's latest ingest and pinned version. Its
    canonical hash is a stable corpus identity without copying the corpus into eval
    artifacts.
    """
    base_url = server_base_url.rstrip("/") + "/"

    def get_json(path: str) -> Any:
        with urlopen(urljoin(base_url, path), timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status} for {path}")
            return json.loads(response.read())

    health = get_json("healthz")
    registries = {domain: get_json(f"v1/domains/{domain}/sources") for domain in domains}
    return {
        "server_base_url": server_base_url,
        "health": health,
        "domains": {
            domain: {
                "source_registry": registry,
                "source_registry_sha256": canonical_hash(registry),
            }
            for domain, registry in registries.items()
        },
    }


class RunArtifacts:
    """Own the manifest and one immutable evidence file per case/trial."""

    def __init__(self, root: Path, manifest: dict[str, Any]) -> None:
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        self.directory = root / run_id
        self.directory.mkdir(parents=True)
        self._manifest_path = self.directory / "manifest.json"
        self._manifest = manifest
        self._write_manifest()

    @property
    def manifest_path(self) -> Path:
        return self._manifest_path

    def record_outcome(self, case_id: str, trial: int, outcome: Any) -> Path:
        case_dir = self.directory / case_id
        case_dir.mkdir(exist_ok=True)
        path = case_dir / f"trial-{trial}.json"
        if path.exists():
            raise RuntimeError(f"refusing to overwrite existing evaluation evidence: {path}")
        payload = {
            "case_id": case_id,
            "trial": trial,
            "passed": outcome.passed,
            "failures": outcome.failures,
            "execution": {
                "model": outcome.evidence.model,
                "session_id": outcome.evidence.session_id,
                "duration_ms": outcome.evidence.duration_ms,
                "exit_code": outcome.evidence.exit_code,
                "usage": outcome.evidence.usage,
                "stderr": outcome.evidence.stderr,
                "tool_calls": [call.as_dict() for call in outcome.evidence.tool_calls],
                "final_answer": outcome.evidence.final_answer,
            },
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")
        self._manifest["attempts"].append(
            {"case_id": case_id, "trial": trial, "passed": outcome.passed, "evidence": str(path.relative_to(self.directory))}
        )
        self._write_manifest()
        return path

    def record_judges(
        self, case_id: str, trial: int, judge_results: list[dict[str, Any]]
    ) -> Path:
        """Write semantic results separately so deterministic evidence stays immutable."""
        case_dir = self.directory / case_id
        case_dir.mkdir(exist_ok=True)
        path = case_dir / f"trial-{trial}-judges.json"
        if path.exists():
            raise RuntimeError(f"refusing to overwrite existing judge evidence: {path}")
        path.write_text(
            json.dumps(judge_results, indent=2, ensure_ascii=False, default=str) + "\n"
        )
        attempt = next(
            item
            for item in self._manifest["attempts"]
            if item["case_id"] == case_id and item["trial"] == trial
        )
        attempt["judge_evidence"] = str(path.relative_to(self.directory))
        self._write_manifest()
        return path

    def finish(self, snapshot: dict[str, Any]) -> None:
        self._manifest["finished_at"] = _utc_now()
        self._manifest["server_after"] = snapshot
        self._manifest["comparable"] = self._manifest["server_before"]["domains"] == snapshot["domains"]
        self._manifest["trial_summary"] = self._trial_summary()
        self._write_manifest()

    def finish_with_server_error(self, error: str) -> None:
        self._manifest["finished_at"] = _utc_now()
        self._manifest["server_after_error"] = error
        self._manifest["comparable"] = False
        self._write_manifest()

    def set_metadata(self, name: str, value: Any) -> None:
        """Add non-secret run configuration discovered by an optional stage."""
        self._manifest[name] = value
        self._write_manifest()

    def _write_manifest(self) -> None:
        self._manifest_path.write_text(
            json.dumps(self._manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        )

    def _trial_summary(self) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for attempt in self._manifest["attempts"]:
            grouped.setdefault(attempt["case_id"], []).append(attempt)
        configured_trials = self._manifest.get("trials_per_case", 1)
        return [
            {
                "case_id": case_id,
                "passed_trials": sum(attempt["passed"] for attempt in attempts),
                "attempted_trials": len(attempts),
                "configured_trials": configured_trials,
                "result": f"{sum(attempt['passed'] for attempt in attempts)}/{configured_trials}",
            }
            for case_id, attempts in sorted(grouped.items())
        ]

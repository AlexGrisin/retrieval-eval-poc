"""Content-addressed local cache for LLM judgments."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from harness.judges.models import JudgeRecord


class JudgeCacheError(RuntimeError):
    pass


class JudgeCache:
    def __init__(self, directory: Path | None) -> None:
        self.directory = directory

    def load(self, key: str) -> JudgeRecord | None:
        if self.directory is None:
            return None
        path = self.directory / f"{key}.json"
        if not path.exists():
            return None
        try:
            record = JudgeRecord.model_validate_json(path.read_text(), strict=True)
        except (OSError, ValidationError) as exc:
            raise JudgeCacheError(f"invalid judge cache entry {path}: {exc}") from exc
        return record.model_copy(update={"cached": True})

    def save(self, record: JudgeRecord) -> None:
        if self.directory is None:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{record.cache_key}.json"
        temporary = self.directory / f".{record.cache_key}.tmp"
        temporary.write_text(record.model_dump_json(indent=2) + "\n")
        temporary.replace(path)

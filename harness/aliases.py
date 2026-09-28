"""Local-only expansion of public case aliases for a private live corpus."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping


PUBLIC_ALIAS_ENV = {
    "ExampleCorp": "EVAL_ALIAS_EXAMPLE_ORGANIZATION",
    "example-developer-portal": "EVAL_ALIAS_EXAMPLE_PORTAL_REPOSITORY",
    "example-scoreboard": "EVAL_ALIAS_EXAMPLE_FEATURE",
}


class AliasConfigurationError(ValueError):
    """A public case alias needs a private local value to run live."""


@dataclass(frozen=True)
class AliasResolver:
    """Expand public aliases for execution and redact them again for evidence."""

    private_by_public: Mapping[str, str]

    @classmethod
    def from_local_environment(
        cls, local_values: Mapping[str, str | None]
    ) -> "AliasResolver":
        # The ignored project .env is deliberately authoritative, matching the
        # judge configuration policy. CI may instead provide these values directly.
        values = {
            name: local_values.get(name) or os.getenv(name, "")
            for name in PUBLIC_ALIAS_ENV.values()
        }
        return cls(
            {
                public: values[environment].strip()
                for public, environment in PUBLIC_ALIAS_ENV.items()
                if isinstance(values[environment], str) and values[environment].strip()
            }
        )

    def expand_case(self, case: dict[str, Any]) -> dict[str, Any]:
        """Convert every public alias used by a case to its private corpus value."""
        return self._replace(case, expanding=True)

    def redact(self, value: Any) -> Any:
        """Replace private corpus values in captured evidence with public aliases."""
        return self._replace(value, expanding=False)

    def _replace(self, value: Any, *, expanding: bool) -> Any:
        if isinstance(value, str):
            return self._replace_text(value, expanding=expanding)
        if isinstance(value, list):
            return [self._replace(item, expanding=expanding) for item in value]
        if isinstance(value, dict):
            return {
                key: self._replace(item, expanding=expanding)
                for key, item in value.items()
            }
        return value

    def _replace_text(self, text: str, *, expanding: bool) -> str:
        if expanding:
            replacements = []
            for public, environment in PUBLIC_ALIAS_ENV.items():
                if public not in text:
                    continue
                private = self.private_by_public.get(public)
                if not private:
                    raise AliasConfigurationError(
                        f"case uses {public!r}; set {environment} in .env or the environment"
                    )
                replacements.append((public, private))
        else:
            replacements = [
                (private, public)
                for public, private in self.private_by_public.items()
            ]
        for source, replacement in sorted(replacements, key=lambda pair: len(pair[0]), reverse=True):
            text = text.replace(source, replacement)
        return text

PYTEST ?= .venv/bin/pytest
CASE ?=
AGENT_TIMEOUT ?= 300

.PHONY: help eval framework list

help:
	@printf '%s\n' \
	  'make eval                         Run every real deployed-skill case.' \
	  'make eval CASE=case-001-sdp-ownership  Run one real case.' \
	  'make framework                    Run fast offline evaluator self-tests.' \
	  'make list                         List tests without running them.'

eval:
	env -u ANTHROPIC_API_KEY $(PYTEST) -m agent_target $(if $(CASE),-k '$(CASE)') --agent-timeout $(AGENT_TIMEOUT) -vv -s

framework:
	$(PYTEST) -m framework -q

list:
	$(PYTEST) --collect-only -q

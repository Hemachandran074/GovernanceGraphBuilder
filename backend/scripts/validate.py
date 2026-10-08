"""End-to-end validation suite for the Governance Graph Builder.

Exercises the running API against all success criteria from the problem
statement. Works against any deployment via the BASE_URL environment variable
(defaults to a local instance), so it doubles as a local check and a post-deploy
smoke test in CI/CD.

Usage:
    uv run python scripts/validate.py
    BASE_URL=https://api.example.com uv run python scripts/validate.py

Exits non-zero if any check fails.

Note: this ingests the sample bundles with reset=true, so it clears the target
graph. Point it at a disposable/validation environment.
"""

from __future__ import annotations

import os
import sys

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")

failures: list[str] = []


def check(label: str, actual, expected) -> None:
    ok = actual == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"       expected: {expected}")
        print(f"       actual:   {actual}")
        failures.append(label)


def names(rows) -> set[str]:
    return {r.get("name") for r in rows}


def main() -> int:
    print(f"Validating {BASE_URL}\n")
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as c:
        # Environment sanity: the API must be ready.
        ready = c.get("/ready")
        check("API readiness", ready.status_code, 200)
        provider = c.get("/graph/stats").json().get("llm_provider")
        print(f"       LLM provider: {provider}\n")

        # ---------------- SC1: simple ----------------
        c.post("/ingest/bundle", json={"bundle": "simple", "reset": True}).raise_for_status()
        check("SC1 simple: tools(Assistant)", names(c.get("/agents/Assistant/tools").json()["results"]), {"calculator"})
        check("SC1 simple: agents(gpt-4o-mini)", names(c.get("/models/gpt-4o-mini/agents").json()["results"]), {"Assistant"})
        check("SC1 simple: access(knowledge-base)", names(c.get("/datasources/knowledge-base/agents").json()["results"]), {"Assistant"})
        check("SC2 simple: no orphans", names(c.get("/agents/orphans").json()["results"]), set())

        # ---------------- SC1/SC2: medium ----------------
        c.post("/ingest/bundle", json={"bundle": "medium", "reset": True}).raise_for_status()
        check("SC1 medium: tools(Support Bot)", names(c.get("/agents/Support Bot/tools").json()["results"]), {"crm-lookup", "email-send"})
        check("SC1 medium: shared model gpt-4o", names(c.get("/models/gpt-4o/agents").json()["results"]), {"Support Bot", "Sales Bot"})
        check("SC1 medium: access(crm-db)", names(c.get("/datasources/crm-db/agents").json()["results"]), {"Support Bot", "Sales Bot"})
        check("SC2 medium: orphan = Triage Bot", names(c.get("/agents/orphans").json()["results"]), {"Triage Bot"})

        # ---------------- SC1/SC2/Bonus: complex ----------------
        c.post("/ingest/bundle", json={"bundle": "complex", "reset": True}).raise_for_status()
        check("SC1 complex: model gpt-4o", names(c.get("/models/gpt-4o/agents").json()["results"]), {"Data Analyst", "Support Agent"})
        check("SC1 complex: access(crm-db) transitive", names(c.get("/datasources/crm-db/agents").json()["results"]), {"Support Agent", "Marketing Agent"})
        check("SC1 complex: access(warehouse-db)", names(c.get("/datasources/warehouse-db/agents").json()["results"]), {"Data Analyst"})
        check("SC1 complex: access(finance-db)", names(c.get("/datasources/finance-db/agents").json()["results"]), {"Data Analyst"})
        check("SC2 complex: orphan = Experimental Agent", names(c.get("/agents/orphans").json()["results"]), {"Experimental Agent"})

        blast = c.get("/tools/crm-lookup/blast-radius").json()
        check("Bonus: blast agents", names(blast["affected_agents"]), {"Support Agent", "Marketing Agent"})
        check("Bonus: blast users", names(blast["affected_users"]), {"Bob"})
        check("Bonus: blast exposed data", names(blast["exposed_data_sources"]), {"crm-db"})

        drift = c.get("/graph/drift").json()
        drift_pairs = {(r["agent"], r["target"]) for r in drift["results"]}
        check("Drift: Support Agent -> shadow-export", ("Support Agent", "shadow-export") in drift_pairs, True)

        # ---------------- SC3: config change reconciles the graph ----------------
        # Fresh, declared-only agent (no runtime logs) so removals delete cleanly.
        def agent_cfg(tools, policies):
            return {
                "id": "agent-sc3",
                "name": "SC3 Agent",
                "owner": {"id": "user-sc3", "name": "SC3 Owner"},
                "model": {"id": "model-sc3", "name": "sc3-model"},
                "tools": [{"id": f"tool-{t}", "name": t} for t in tools],
                "policies": [{"id": f"policy-{p}", "name": p} for p in policies],
            }

        c.post("/ingest/agent-config", json={"config": agent_cfg(["alpha", "beta"], ["sc3pol"]), "reset": True}).raise_for_status()
        check("SC3 before: tools", names(c.get("/agents/SC3 Agent/tools").json()["results"]), {"alpha", "beta"})
        check("SC3 before: not orphan", "SC3 Agent" in names(c.get("/agents/orphans").json()["results"]), False)

        # Remove a tool and the policy; re-ingest without reset.
        c.post("/ingest/agent-config", json={"config": agent_cfg(["alpha"], []), "reset": False}).raise_for_status()
        check("SC3 after: stale tool removed", names(c.get("/agents/SC3 Agent/tools").json()["results"]), {"alpha"})
        check("SC3 after: now orphan (policy removed)", "SC3 Agent" in names(c.get("/agents/orphans").json()["results"]), True)

    print("\n" + ("ALL CHECKS PASSED" if not failures else f"FAILURES ({len(failures)}): {failures}"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

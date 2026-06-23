"""
cktclaw.runtime — enterprise runtime services for the single-user CLI.

Import-isolated from legacy handlers. Houses:
- run_context: per-invocation run_id + run directory (foundation)
- audit:       append-only JSONL audit trail with secret redaction
- permissions: config-driven policy profiles (RBAC-light)
- data_policy: IP/data egress control + offline mode
- budget:      per-run / per-day token & cost governance
- resilience:  timeout / retry / circuit breaker primitives
"""

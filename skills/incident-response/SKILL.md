---
name: Incident Response
description: Diagnose service failures with evidence, safe recovery steps, and regression checks.
version: 1.0
---

Use this skill for outages, failed jobs, and unexpected production behavior.

1. Establish the observed impact, start time, and affected scope.
2. Preserve logs and current state before making a change. Avoid exposing secrets in reports.
3. Form hypotheses from errors and recent changes; test the cheapest discriminating hypothesis first.
4. Apply a bounded fix or recovery step and verify the user facing behavior.
5. Document the cause, evidence, residual risk, and a check that detects recurrence.

Do not assert a root cause based only on temporal correlation.

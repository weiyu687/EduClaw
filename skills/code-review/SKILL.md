---
name: Code Review
description: Inspect software changes for concrete regressions and verify findings with focused tests.
version: 1.0
---

Use this skill when reviewing a patch or repository.

1. Read the requested diff and the surrounding call sites before drawing conclusions.
2. Prioritize correctness, security, compatibility, and behavior the user can observe.
3. Reproduce a suspected failure or write a focused check when practical.
4. Give each finding an exact file and line, a triggering condition, and the resulting impact.
5. Distinguish confirmed defects from risks and questions. If no defects are found, say what was examined and tested.

Do not claim tests passed unless they were actually run.

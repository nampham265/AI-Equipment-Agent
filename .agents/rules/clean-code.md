---
trigger: always_on
description: Clean-code, safety, and restrained UI rules for this workspace.
---

- Follow the workspace `AGENTS.md` and `docs/` as the source of truth for requirements.
- Keep functions focused and files reasonably small. Avoid giant components and giant service classes.
- Validate all incoming form/API data on the backend, not only in the browser.
- Use repositories/services to isolate persistence and business rules.
- Keep prompts, provider settings, list identifiers, and credentials out of source code.
- Never treat model-generated text as trusted data. Validate structured model output against a schema.
- Never let the LLM directly write arbitrary database fields or approve/reject requests.
- Use simple Vietnamese UI copy and few, purposeful icons.
- Do not insert real company inventory or confidential information into sample data, tests, screenshots, or documentation.

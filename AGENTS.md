# Workspace instructions — AI Equipment Assistant V1

## Product goal
Build a complete, runnable V1 web application for an AI assistant that helps users find technical equipment, submit borrowing requests, and helps a manager review requests with AI-generated priority recommendations. The manager—not the AI—makes the approval decision.

## Read first
Before changing files, read:
- `docs/PRODUCT_PLAN.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_MODEL.md`
- `docs/AI_POLICY.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/ACCEPTANCE_CRITERIA.md`
- `docs/PRIVACY_AND_SECURITY.md`

## Required approach
- Deliver an end-to-end runnable vertical slice, not just a scaffold, mockup, or isolated components.
- Default to local mode so the app can be run and tested without Microsoft credentials or an AI API key.
- Keep data access behind repository interfaces. Implement the local SQLite repository first. Add Microsoft Lists integration behind configuration and do not claim it works until it has been tested with valid credentials and list identifiers.
- Keep AI behind a provider/service interface. Use structured outputs and validate them before saving. If the real AI provider is not configured, use a clearly labelled demo fallback.
- The AI may recommend priority and explain its evidence. It must never approve or reject a request autonomously.
- Do not infer project importance from a project name. There is no reliable project registry in V1.
- Never calculate availability from total quantity alone. Consider confirmed overlapping requests/loans and the requested date range.
- Use synthetic sample equipment only in the repository. Never add real Bosch inventory, credentials, tokens, internal documents, or internal URLs to Git.

## Clean code
- Use clear module boundaries: API routes, schemas, services, repositories, AI provider, notification provider, and UI components.
- Avoid huge files, duplicated business logic, circular imports, magic strings/numbers, and unnecessary abstractions.
- Use Python type hints, Pydantic validation, explicit TypeScript types, and descriptive names.
- Keep routes/controllers thin. Business rules belong in services, not UI components or route handlers.
- Centralize configuration in environment variables and validate required settings at startup.
- Add tests for availability calculations, request state transitions, priority output validation, and API workflows.
- Handle errors visibly and safely. Never expose stack traces, secrets, or internal IDs unnecessarily to end users.
- Do not add LangChain, a vector database, multi-agent orchestration, or other large frameworks unless a demonstrated V1 requirement needs them.

## UI and writing style
- User-facing language: Vietnamese. Keep product/technology terms in English only where useful and use them consistently.
- Use a restrained, professional interface: clear hierarchy, whitespace, readable forms and tables.
- Do not overuse icons, emoji, badges, animations, gradients, or decorative cards. Use an icon only when it improves comprehension.
- Provide labels, keyboard focus, sensible empty states, loading states, and error states.
- Prioritize functional clarity over visual decoration.

## Completion discipline
- Do not stop after making a plan or creating a scaffold. Implement the complete local V1, run tests, start the app, and fix issues.
- Before finishing, report what works, commands used, tests run, what still requires credentials, and any limitations honestly.

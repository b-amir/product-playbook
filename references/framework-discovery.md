# Framework and product-surface discovery

## Contents

1. Browser frontends
2. Viewport and responsive forks
3. APIs and backends
4. Services and workers
5. RAG and retrieval products
6. Libraries, SDKs, and helper packages
7. Integrations, extensions, data, and tooling
8. Command-line products
9. Mobile products
10. Full-stack products
11. Contracts and runtime addresses
12. Unknown frameworks
13. Mixed and multi-root products
14. Auth, SSO, and identity
15. Webhooks and async delivery
16. Feature flags and experiments
17. Internationalization and locale packs
18. Accessibility smoke
19. Source priority

## Browser frontends

### Playwright

Look for:

- `playwright.config.*`
- `@playwright/test` or `playwright` dependencies
- `*.spec.*` files under `e2e`, `tests`, or `playwright`
- Fixtures, storage state, global setup, and web-server configuration
- Accessible locators such as `getByRole`, `getByLabel`, `getByPlaceholder`, and `getByText`

Treat visible assertions as expected-result evidence. Trace helpers and fixtures before assigning a
persona, route, or starting state.

### Cypress

Look for:

- `cypress.config.*`
- A `cypress/e2e` tree
- `*.cy.*` files
- Custom commands, fixtures, intercepts, and support files
- `cy.contains`, `findByRole`, `findByLabelText`, and visible-text assertions

Trace custom commands before translating them. Do not expose command or selector names in manual
steps.

### Selenium and WebDriver

Look for:

- Selenium or WebDriver dependencies in JavaScript, Python, Java, C#, or Ruby projects
- Browser setup and session fixtures
- Page-object classes
- Test files using `By`, `WebDriverWait`, or equivalent APIs
- CI jobs that start a browser

Do not treat page-object method names as visible UI evidence.

## Viewport and responsive forks

Expand this probe only when browser or hybrid UI evidence exists. Do not add
viewport sections to every scenario.

### Signals to scan

Look for evidence that the same journey can diverge by width or device class:

| Class | Evidence examples |
| --- | --- |
| CSS breakpoints | `@media`, Tailwind or similar `sm:` / `md:` / `lg:` layout forks, theme breakpoints |
| Layout forks | Separate mobile and desktop components, drawer vs sidebar, `*Mobile*` / `*Desktop*` modules |
| Runtime forks | `matchMedia`, `useMediaQuery`, `useBreakpoint`, `innerWidth`, resize listeners |
| Conditional UI or auth | Permission, role, or feature gates wrapped in viewport branches. Mobile-only or desktop-only actions |
| Tests | Playwright `setViewportSize` or device projects, Cypress `cy.viewport`, responsive e2e matrices |

Discovery may list `viewport_fork_candidates` when these markers appear. Treat that list as a
lead for Plan, not as proof of divergent outcomes.

### When to mark a scenario

Mark a scenario `viewport_sensitive` only when its linked routes, components, or tests hit these
signals for the journey under change. Shared global CSS alone is not enough.

When marked:

- Plan Notes should say `viewport: yes` plus a short evidence hint
- Publish an **Across viewports** section per [output-contract.md](output-contract.md)
- Prefer the product's evidenced breakpoints. Otherwise use one narrow and one wide width
- State what must match across widths (especially permissions and primary actions)
- State intentional differences when evidence shows them

When unmarked, omit **Across viewports**. Do not invent mobile-only or desktop-only behavior.

Native mobile apps use the Mobile products section. Do not conflate responsive web forks with
native device matrices unless the same journey is proven on both surfaces.

## APIs and backends

Look for:

- OpenAPI, Swagger, AsyncAPI, GraphQL, protobuf, or RAML contracts
- Route, controller, endpoint, handler, serializer, and schema modules
- API client tests and integration tests
- Authentication, authorization, validation, pagination, error, retry, and idempotency assertions
- Framework-specific test clients

Common test and application signals include:

| Ecosystem | Test signals | Application signals |
| --------- | ------------ | ------------------- |
| Python | pytest, unittest, TestClient, httpx | FastAPI, Flask, Django |
| JavaScript or TypeScript | Jest, Vitest, Supertest | Express, NestJS, Fastify |
| Java or Kotlin | JUnit, MockMvc | Spring |
| Go | `_test.go`, `httptest` | Gin, Fiber, standard HTTP |
| .NET | xUnit, NUnit, MSTest | ASP.NET Core |
| Ruby | RSpec request specs | Rails, Sinatra |
| Rust | Cargo tests | Axum, Actix |

For API scenarios, copy exact methods, paths, field names, status codes, and observable response
properties from contracts or tests. Never invent request examples.

## Services and workers

Look for:

- Queue consumers and producers
- Background jobs and schedulers
- Webhook handlers
- Event schemas and contract tests
- Retry, dead-letter, timeout, deduplication, and idempotency tests
- Observable status records, notifications, logs, or downstream effects

Write a manual scenario only when a tester has a supported trigger and an observable outcome.
Otherwise document the gap instead of exposing an internal implementation recipe.

## RAG and retrieval products

Look for:

- Retrieval, embedding, reranking, chunking, indexing, and vector-store modules
- Prompt construction, guardrails, PII handling, source filtering, and output sanitization
- Evaluation datasets, golden sets, relevance metrics, and regression thresholds
- Vault, tenant, client, role, expiry, and document-status filters
- Supported search, answer, indexing, evaluation, or administration interfaces

Do not turn internal retrieval functions into manual procedures. Require a supported API, CLI,
job, UI, or evaluation command and an observable result. Distinguish an executable RAG service
from a helper library, fixture corpus, generated report, or documentation-only design.

## Libraries, SDKs, and helper packages

Look for:

- Package exports, public modules, generated clients, type declarations, and examples
- Consumer contract tests and compatibility matrices
- Helper packages under `packages`, `libs`, `shared`, `common`, `sdk`, or client roots
- Documented commands or sample applications that expose observable behavior

Treat a package as an independent surface when consumers can exercise a stable public interface.
Keep it as supporting evidence when it only implements an internal step in a larger journey.

## Integrations, extensions, data, and tooling

Look for:

- Connectors, adapters, webhooks, sync jobs, and external-system contracts
- Editor or browser extension manifests, commands, activation events, and UI contributions
- Data pipelines, DAGs, transformations, scheduled jobs, and observable outputs
- Generators, reporting tools, workspace automation, and developer CLIs

Do not collapse these into frontend or backend merely because they share a language. Record their
own operators, triggers, configuration, cleanup, and failure surfaces.

## Command-line products

Look for:

- Command registration and help output
- Click, Typer, argparse, Commander, Cobra, Clap, or similar dependencies
- CLI runners and subprocess-based tests
- Exit-code, stdout, stderr, file-output, and configuration assertions

Copy commands and options exactly. Use safe placeholders for paths, identifiers, and secrets.

## Mobile products

Look for:

- React Native, Flutter, Android, iOS, or SwiftUI manifests
- Detox, Appium, XCTest, Espresso, or Flutter integration tests
- Permission prompts, navigation stacks, offline behavior, deep links, and device-specific states

Record the device, operating-system version, orientation, and permission state needed by each
scenario.

## Full-stack products

Prefer user journeys as the main scenarios. Add API or service checks only when they are necessary
to prepare data, verify an invisible outcome, or isolate a failure. Map frontend and backend
evidence to the same scenario when both establish one journey.

## Contracts and runtime addresses

Look for:

- OpenAPI, Swagger, AsyncAPI, GraphQL, protobuf, and RAML artifacts
- Generated schemas and clients
- Cached contract copies in frontend, test, fixture, generated, or build-input directories
- OpenAPI `servers`, API documentation URLs, local development URLs, WebSocket URLs, and runtime
  address environment-variable names
- Route registration, handlers, request and response models, permissions, errors, retries, and
  integration behavior in implementation source

Classify each item as a contract artifact, cached or generated derivative, fixture, tooling, or
documentation reference. A frontend cache proves the consumer snapshot, not automatically the
current backend deployment. Compare metadata and behavior before choosing a source of truth.

Report Git remotes separately from runtime product addresses. Sanitize credentials and query
parameters. Never read or publish secret-file values.

## Unknown frameworks

Look for:

- Repository instruction files
- Test commands and CI jobs
- Makefiles, task runners, workspace manifests, and executable scripts
- Browser, HTTP, CLI, queue, or device drivers
- Setup fixtures and test naming conventions
- Actions followed by observable assertions

Report discovered evidence without forcing it into a known framework.

## Mixed and multi-root products

Keep every detected surface and component. Do not collapse a repository to one surface merely
because an API, frontend, CLI, worker, RAG, library, integration, tooling, data, extension, or
mobile dependency appears first.

Use stable source IDs across runs. Merge evidence into one journey when a tester operates one
interface flow. Keep component-specific scenarios when different operators, interfaces, setup, or
failure evidence make them independently executable.

When only some sources are accessible, bound coverage claims to those sources and preserve
out-of-scope scenarios.

## Auth, SSO, and identity

When evidence exists, look for:

- OAuth/OIDC, SAML, magic-link, passkey, or session fixtures
- IdP configuration names visible to testers (not secret values)
- Role and permission matrices asserted in tests
- Login, logout, refresh, invite, and account-switch journeys

Publish only steps a tester can perform on a supported interface. Never publish client secrets.

## Webhooks and async delivery

Look for:

- Webhook route tests, signature verification, retry and dead-letter assertions
- Delivered event payloads and observable downstream side effects
- Supported ways to trigger or simulate delivery in non-production

Write a scenario only when the tester has a safe trigger and an observable outcome.

## Feature flags and experiments

Look for:

- Flag keys referenced in tests or docs
- Variants required to reach a journey
- Environment-owner instructions to enable a disposable flag state

Name flags exactly as evidenced. Do not invent flag keys.

## Internationalization and locale packs

Look for:

- Locale files, i18n test matrices, language switchers
- Assertions on translated visible strings for a specific locale

When multiple locales are first-class, either scope scenarios to one approved locale or add
locale-specific expected labels from evidence. Do not invent translations.

## Accessibility smoke

When UI tests or docs assert accessibility, adapt the quality sweep to include:

- Keyboard reachability for primary journeys
- Visible name / role expectations already asserted in tests
- Contrast or a11y scanner gates only when the product exposes a supported check

Do not invent WCAG citations the repository does not use.

## Source priority

Apply the relevant order to a specific claim:

1. Successful current observation through the supported product interface
2. Passing current end-to-end or integration test
3. Test source read but not executed now
4. Executable contract and application source
5. Technical documentation
6. Existing playbook prose

Treat existing playbook prose as a reconciliation candidate, never as independent evidence. Record
all disagreements between levels.

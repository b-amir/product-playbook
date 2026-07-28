# Framework and product-surface discovery

## Contents

1. Browser frontends
2. APIs and backends
3. Services and workers
4. Command-line products
5. Mobile products
6. Full-stack products
7. Unknown frameworks
8. Mixed and multi-root products
9. Source priority

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
because an API, frontend, CLI, worker, or mobile dependency appears first.

Use stable source IDs across runs. Merge evidence into one journey when a tester operates one
interface flow. Keep component-specific scenarios when different operators, interfaces, setup, or
failure evidence make them independently executable.

When only some sources are accessible, bound coverage claims to those sources and preserve
out-of-scope scenarios.

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

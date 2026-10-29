# Environment capabilities

Some scenarios depend on things only certain environments have: object storage, a queue, a
paid model, real cloud permissions. A test that cannot run because of the environment is not a
product defect. Record it as **E** (Blocked, environment) so the report separates "the code is
wrong" from "this environment cannot show it".

## Contents

1. Vocabulary
2. Declaring requires and provides
3. Results
4. Local emulators
5. Mocking LLM and OCR providers
6. Golden sets
7. Checklist

## Vocabulary

Declare capability names once in `playbook-tests.json`. When the `capabilities` object exists,
the checker rejects any name not listed in it.

```json
"capabilities": {
  "s3": "S3-compatible object storage the app can reach",
  "sqs": "SQS-compatible queue with a dead-letter queue",
  "llm-mock": "Mock model endpoint with recorded and failure responses",
  "llm-real": "The real paid model provider",
  "real-iam": "Real cloud identity and permissions"
}
```

Name the behaviour, not the vendor host. Keep an emulator and the real service apart only when a
test truly needs the real one (`real-iam`, `llm-real`); otherwise one name covers both.

## Declaring requires and provides

```json
"targets": {
  "local": {"kind": "local", "base_url": "http://127.0.0.1:3000",
            "provides": ["s3", "sqs", "llm-mock"],
            "notes": "s3 and sqs via an emulator stack, llm-mock via a mock server"},
  "dev":   {"kind": "dev", "base_url_env": "PLAYBOOK_DEV_URL",
            "provides": ["s3", "sqs", "llm-real", "real-iam"]}
},
"scenarios": {
  "JOB-01": {"requires": ["s3", "sqs"], "tags": ["destructive"], "...": "..."}
}
```

- `provides` lists what the environment really offers. Never list a capability that is only
  planned.
- `--provide s3,sqs` adds capabilities for one run, for example after starting the emulators.
- The runner exports `PLAYBOOK_PROVIDES` (comma list) so a test can check for itself.
- A test that discovers a missing dependency at run time skips with a reason that starts with
  `[env]`, for example `pytest.skip("[env] needs s3: storage returned 503")`. If every test in
  the scenario skips that way, the result is E, not B.

In the playbook, put the same need in the scenario's **Environment** section in plain words
("needs real object storage"), never a host name, bucket, or URL.

## Results

| Letter | Meaning |
| --- | --- |
| P | Passed |
| F | Failed: the product or the test is wrong |
| B | Blocked: skipped, timed out, runner missing, precondition not met |
| E | Blocked (environment): the target lacks a required capability |
| U | Not built yet: the feature is not in the code, or its ticket is not ready ([runs.md](runs.md)) |
| N | Not applicable or not selected |

The summary prints an `Environment:` line listing E scenarios. E never makes the run exit 1.
Report E items to whoever owns the environment, F items as bugs.

## Local emulators

Use an emulator when the code talks to a cloud API through a configurable endpoint:

- LocalStack or similar for S3, SQS, SNS, DynamoDB. Create buckets and queues with an init
  script so a fresh stack is ready, and mirror production settings that change behaviour
  (visibility timeout, dead-letter `maxReceiveCount`, CORS for presigned uploads).
- MinIO for S3-only needs.
- Check that the product accepts a custom endpoint (for example `AWS_ENDPOINT_URL`). If it does
  not, do not patch the product from the tests; record a change request and mark the scenarios E
  on local.
- Emulators prove the code path, not cloud configuration. Keep `real-iam` (policies, KMS, bucket
  policies) for a real environment.

## Mocking LLM and OCR providers

Point the product at a small mock server with the same request and response shape:

- Serve recorded or synthetic responses keyed by input, never real customer documents.
- Add switchable failure modes: timeout, 429 with `Retry-After`, 5xx, malformed JSON, empty
  result. Each maps to a scenario that checks retries, attempt limits, rate caps, and the error
  shown to the user.
- Let tests read back what the mock received (request count, timing) so caps and retries are
  observable.
- The mock proves parsing and error handling. It cannot prove extraction quality.

## Golden sets

Quality of a real model or OCR provider needs a golden set:

- A small fixed set of synthetic or approved documents with expected field values.
- Score per field with tolerances (numbers within a delta, text normalised), and pass on a
  threshold rather than exact equality.
- Tag these scenarios `destructive` when they cost money, require `llm-real` (or similar), and
  never run them on prod by default.

## Checklist

- [ ] Capability names declared once and used consistently
- [ ] Each target lists only what it really provides
- [ ] Emulator init creates every resource the code expects
- [ ] Product supports a custom endpoint, or a change request is recorded
- [ ] Mock covers success and each failure mode the code handles
- [ ] Golden-set scenarios require the real provider and are excluded from default runs
- [ ] Report lists E separately from F

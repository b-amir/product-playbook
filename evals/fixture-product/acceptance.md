# Accounts acceptance examples

## EX-1.1-1 Create an account
- Given the accounts API is reachable
- When a client sends `POST /accounts` with a non-empty `name`
- Then the response status is `201`
- And the body contains an `id` and the same `name`

## EX-1.1-2 Reject an empty name
- Given the accounts API is reachable
- When a client sends `POST /accounts` with an empty `name`
- Then the response status is `400`

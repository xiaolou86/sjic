# License deployment notes

## Behavior

- If `backend/license.json` does not exist:
  - Backend runs in `trial` mode for 30 days.
  - Camera quota uses `license.trial_max_cameras` in `backend/config.yaml`.
- If `backend/license.json` exists:
  - Backend runs in `official` mode.
  - Validates `machine_code`, `expires_at`, `max_cameras`, and `allowed_algorithms`.

## File format

Use `backend/license.example.json` as template.

Required fields:

- `edition`: `official`
- `machine_code`: backend machine fingerprint hash
- `max_cameras`: max allowed camera count, `<=0` means unlimited
- `allowed_algorithms`: empty array means all algorithms allowed
- `expires_at`: ISO-8601 datetime with timezone, e.g. `2027-12-31T23:59:59+00:00`

## Runtime constraints

- Camera create API checks camera quota.
- Task create/update/start checks algorithm entitlement.
- Algorithm list API is filtered by `allowed_algorithms` when configured.
- Deleting a camera cascades: stop edge tasks via MQTT then remove related `tasks` rows.

## Machine code

Query runtime machine code via API:

- `GET /api/license/status`

Response contains `machine_code`.

## Suggested rollout

1. Start backend without license file and verify trial mode.
2. Read `machine_code` from `/api/license/status`.
3. Generate `license.json` from template.
4. Place file at `backend/license.json` and restart backend.

# Algorithm publish workflow

## Concept

"Publish algorithm version" means:

- choose one algorithm template
- bind one model asset (`model_id`) as the active runtime model
- optionally set default labels for this algorithm

After publishing, task creation only needs `algorithm_id`; model selection is no longer exposed in task UI.

## API

- `POST /api/algorithms/{alg_id}/publish`

Request body:

```json
{
  "model_id": 12,
  "labels": [0, 2, 5]
}
```

Notes:

- `model_id` is required.
- `labels` is optional; omit to keep existing default labels.
- endpoint requires `vendor` role.

## Runtime behavior

- Task create/update ignores `modelId` from client payload.
- Detector start resolves model from `algorithm.model_id`.
- If algorithm has no bound model, task create/start will fail with explicit error.

## Recommended operator steps

1. Upload/maintain model in model center (vendor only).
2. Open algorithm center and publish the algorithm with target model.
3. Customer admin creates tasks by selecting only algorithm + camera + node + thresholds.

# ml/

Analytics research utilities. They read **real stored data** from Neon and never write to it.
The production analytics (ST-DBSCAN clustering, persistence, explainable scoring) live in
`backend/app/analytics/` so the API and pipeline share one implementation.

| Script | Purpose |
|--------|---------|
| `evaluate_clustering.py` | Parameter sensitivity of ST-DBSCAN (`eps_km` x `max_gap_hours`) on stored detections - evidence for the chosen defaults. |
| `export_features.py` | Exports per-cluster features + engine assessments to CSV - the training table for a future supervised classifier once analysts label incidents. |
| `models/` | Reserved for trained model artefacts (Stage 2+). Empty by design: no model is claimed before labelled data exists. |

Run from the repository root with the backend virtualenv, e.g.

```bash
backend/.venv/Scripts/python ml/evaluate_clustering.py --days 10
```

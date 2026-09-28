# Arogya Backend (FastAPI)

Population health management API — longitudinal patient journeys for cancer, diabetes and maternal health.

## Run locally

```bash
pip install -r requirements.txt
python main.py            # http://localhost:8000  (docs at /docs)
```

Data auto-seeds on first boot (52 realistic patients). Re-seed: `python seed.py --force`.

## Deploy to GCP Cloud Run

```bash
gcloud run deploy arogya-api \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated
```

Container listens on `$PORT` (8080). Note: JSON-file storage is ephemeral on Cloud Run —
mount a GCS/volume or swap to Cloud SQL/Firestore for production persistence.

## Key endpoints

| Route | Purpose |
|---|---|
| `GET /api/dashboard` | Population KPIs, stage/condition/risk distributions, care gaps |
| `GET/POST /api/patients` | Registry + registration |
| `GET /api/patients/{id}` | Full longitudinal record + computed journey |
| `POST /api/patients/{id}/consultations · investigations · biopsies · referrals · prescriptions · advice · followups · reports` | Workflow writes |
| `PATCH /api/investigations/{id}` etc. | Status transitions |
| `GET /api/registry` | Disease-registry grouping with journey progress |
| `GET /api/care-gaps` | Population care-gap detection |
| `POST /api/ai` | AI assistant (rule-based population queries) |

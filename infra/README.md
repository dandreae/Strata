# infra

Deliberately minimal for this pass — no Terraform/Kubernetes yet, per
project scope. This directory exists to hold deployment groundwork as it's
added, and to document the intended shape ahead of time.

## Planned (not yet created)

- `cloudrun/` — Cloud Run service definitions (backend API) and, if slicing
  moves to its own service, a slicer-worker service.
- `cloudbuild.yaml` or a GitHub Actions workflow — build + push the backend
  image, deploy to Cloud Run.
- Firestore security rules / indexes, once `FirestoreRunRepository` exists.
- Cloud Storage bucket lifecycle rules (STL uploads and generated G-code
  don't need to live forever).

## Manual GCP setup (for the hackathon demo, not automated yet)

1. `gcloud services enable run.googleapis.com firestore.googleapis.com storage.googleapis.com`
2. Create a Cloud Storage bucket for STL/G-code artifacts.
3. Create a Firestore database (Native mode).
4. Build and deploy the backend image to Cloud Run (see `backend/Dockerfile`),
   with `STRATA_STORAGE_BACKEND=gcs`, `STRATA_REPOSITORY_BACKEND=firestore`,
   `STRATA_GCP_PROJECT_ID`, `STRATA_GCS_BUCKET_NAME` set as env vars/secrets
   — once those backends are implemented (see docs/architecture.md).

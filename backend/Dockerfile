# Strata backend — development/Cloud Run image.
#
# PrusaSlicer is intentionally NOT installed in this image yet. Doing so
# requires a headless PrusaSlicer build (with its X11/OpenGL dependencies
# handled for a container) which needs to be verified against a real
# PrusaSlicer release before baking it in. Until then, PrusaSlicerService
# will raise SlicerUnavailableError inside this container — expected and
# handled cleanly by the app. See docs/architecture.md for the plan to add
# it (either apt-installing a headless build, or a separate slicer-worker
# image invoked as a Cloud Run Job).

FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal on purpose — add PrusaSlicer's runtime
# dependencies here once the headless install path is verified.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

# Cloud Run injects $PORT; default to 8080 for local `docker run`.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

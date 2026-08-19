# Strata backend — Cloud Run image, with a real PrusaSlicer CLI baked in.
#
# Base image is pinned to python:3.12-slim-trixie (Debian 13 "trixie")
# specifically because Debian packages PrusaSlicer directly via apt, and
# trixie is the first Debian release carrying the 2.9.x generation
# (2.9.2+dfsg-1) — the same CLI generation as the PrusaSlicer 2.9.6 binary
# this codebase's command construction/G-code parsing was verified against
# locally (see app/slicer/prusaslicer.py's module docstring). Debian
# bookworm only has 2.5.0+dfsg-4, an older CLI generation — deliberately
# avoided. Confirmed against packages.debian.org (trixie), not guessed.
#
# PrusaSlicer is NOT distributed as a Linux AppImage past 2.8.1 (Prusa
# moved to Flatpak-only for Linux from 2.9.0 on) and Flatpak is a poor fit
# for a container (wants D-Bus/OSTree/bwrap sandboxing that conflicts with
# Cloud Run's gVisor sandbox) — apt is the real, authoritative Linux
# install path here, not a fallback choice.
#
# The Debian package pulls in PrusaSlicer's full GUI dependency stack
# (GTK3/OpenGL/wxWidgets/WebKit) — Debian ships no separate console-only
# package. Xvfb is deliberately NOT installed here; it is only added if a
# real containerized `--export-gcode` run demonstrates PrusaSlicer actually
# requires a live display (see docs/architecture.md for the verified
# outcome).

FROM python:3.12-slim-trixie

WORKDIR /app

# build-essential: for any backend deps with C extensions.
# prusa-slicer: exact-pinned Debian trixie package (see header above).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    prusa-slicer=2.9.2+dfsg-1 \
    && rm -rf /var/lib/apt/lists/*

# Build-time sanity check: fail the image build itself, not the first
# request, if the installed binary can't even report its own version.
RUN prusa-slicer --help >/dev/null

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

# Cloud Run injects $PORT; default to 8080 for local `docker run`.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

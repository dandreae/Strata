"""Service-layer abstractions: storage and persistence.

Each service is defined as an abstract interface plus a local/dev
implementation, so a cloud-backed implementation (Google Cloud Storage,
Firestore) can be substituted later without touching callers.
"""

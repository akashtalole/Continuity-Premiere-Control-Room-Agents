"""Firestore client for incident data -- see app/services/incident_store.py
for the actual read/write logic. This module owns just the client
singleton and collection-name constants.

Auth: the async client uses Application Default Credentials -- the Cloud
Run service account's ADC in production (granted roles/datastore.user by
infra/scripts/00-setup.sh), or `gcloud auth application-default login`
locally. Setting FIRESTORE_EMULATOR_HOST (as the test suite does) routes
every call to a local emulator instead, ignoring real credentials entirely
-- this is the standard google-cloud-firestore behavior, not something
this module implements itself.

Why Firestore only for incident data and not everything: this is a
schema-less, high-write, timeline-shaped dataset (agent events, token
usage) that suits a document store well and needs no relational
constraints. Users/audit log/workspaces stay on SQL (app/db.py) since
unique-email constraints and audit queries fit relational storage better.
"""

from functools import lru_cache

from google.cloud.firestore import AsyncClient

from app.config import get_settings

INCIDENTS_COLLECTION = "incidents"
AGENT_EVENTS_SUBCOLLECTION = "agent_events"
TOKEN_USAGE_SUBCOLLECTION = "token_usage"


@lru_cache
def get_firestore_client() -> AsyncClient:
    settings = get_settings()
    project = settings.firestore_project_id or settings.google_cloud_project or None
    return AsyncClient(project=project)

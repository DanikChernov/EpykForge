#!/usr/bin/env bash
set -euo pipefail

python infra/cloud/deploy_agents.py \
  --project "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}" \
  --location "${GOOGLE_CLOUD_LOCATION:-us-central1}" \
  --bucket "${FORGE_AGENT_STAGING_BUCKET:?Set FORGE_AGENT_STAGING_BUCKET}"

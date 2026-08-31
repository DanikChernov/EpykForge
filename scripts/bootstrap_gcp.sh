#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="epykforge-507203"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"

gcloud config set project "epykforge-507203"
gcloud config set account "chessmaster212121@gmail.com"
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  pubsub.googleapis.com \
  firestore.googleapis.com \
  secretmanager.googleapis.com \
  cloudtrace.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  artifactregistry.googleapis.com

echo "Google Cloud project bootstrapped for EPYK Forge in $REGION."

#!/usr/bin/env bash
set -euo pipefail

REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
gcloud run services delete forge-web --region "$REGION" --quiet || true
gcloud run services delete forge-api --region "$REGION" --quiet || true
echo "Deleted Cloud Run demo services. Terraform-managed resources should be destroyed with terraform destroy."

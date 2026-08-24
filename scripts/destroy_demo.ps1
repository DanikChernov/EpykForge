$ErrorActionPreference = "Stop"

$Region = if ($env:GOOGLE_CLOUD_LOCATION) { $env:GOOGLE_CLOUD_LOCATION } else { "us-central1" }
gcloud run services delete forge-web --region $Region --quiet
gcloud run services delete forge-api --region $Region --quiet
Write-Host "Deleted Cloud Run demo services. Terraform-managed resources should be destroyed with terraform destroy."

locals {
  service_prefix = "epyk-forge"
  topics = [
    "factory-events",
    "incident-events",
    "agent-tasks",
    "action-results",
    "notifications",
  ]
}

resource "google_project_service" "services" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "firestore.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudtrace.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "artifactregistry.googleapis.com",
  ])

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

resource "google_pubsub_topic" "topics" {
  for_each = toset(local.topics)
  name     = "${local.service_prefix}-${each.key}"

  depends_on = [google_project_service.services]
}

resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.services]
}

resource "google_service_account" "api" {
  account_id   = "epyk-forge-api"
  display_name = "EPYK Forge API"
}

resource "google_project_iam_member" "api_roles" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/datastore.user",
    "roles/pubsub.publisher",
    "roles/pubsub.subscriber",
    "roles/secretmanager.secretAccessor",
    "roles/cloudtrace.agent",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_cloud_run_v2_service" "api" {
  name     = "forge-api"
  location = var.region

  template {
    service_account = google_service_account.api.email
    containers {
      image = var.api_image
      ports {
        container_port = 8080
      }
      env {
        name  = "FORGE_ENV"
        value = "production"
      }
      env {
        name  = "FORGE_STORE_BACKEND"
        value = "firestore"
      }
      env {
        name  = "FORGE_EVENT_BUS"
        value = "pubsub"
      }
      env {
        name  = "FORGE_MODEL_PROVIDER"
        value = "REAL_GEMINI"
      }
      env {
        name  = "FORGE_GEMINI_MODEL"
        value = var.gemini_model
      }
      env {
        name  = "GOOGLE_GENAI_USE_ENTERPRISE"
        value = "True"
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = "global"
      }
    }
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
  }

  depends_on = [google_project_iam_member.api_roles]
}

resource "google_cloud_run_v2_service" "web" {
  name     = "forge-web"
  location = var.region

  template {
    containers {
      image = var.web_image
      ports {
        container_port = 8080
      }
    }
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
  }

  depends_on = [google_project_service.services]
}

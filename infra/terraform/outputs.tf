output "api_url" {
  value = google_cloud_run_v2_service.api.uri
}

output "web_url" {
  value = google_cloud_run_v2_service.web.uri
}

output "pubsub_topics" {
  value = [for topic in google_pubsub_topic.topics : topic.name]
}

variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "Google Cloud region for Cloud Run and regional services."
  type        = string
  default     = "us-central1"
}

variable "api_image" {
  description = "Container image for forge-api."
  type        = string
}

variable "web_image" {
  description = "Container image for forge-web."
  type        = string
}

variable "gemini_model" {
  description = "Gemini model ID."
  type        = string
  default     = "gemini-3.5-flash"
}

variable "web_origin" {
  description = "Optional deployed forge-web origin allowed by forge-api CORS."
  type        = string
  default     = null
}

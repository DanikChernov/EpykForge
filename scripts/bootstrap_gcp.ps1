param(
  [string]$ProjectId = $env:GOOGLE_CLOUD_PROJECT,
  [string]$Region = $env:GOOGLE_CLOUD_LOCATION
)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
  $PSNativeCommandUseErrorActionPreference = $false
}

if ([string]::IsNullOrWhiteSpace($ProjectId)) {
  throw "Set GOOGLE_CLOUD_PROJECT"
}

if ([string]::IsNullOrWhiteSpace($Region)) {
  $Region = "us-central1"
}

function Get-GCloudCommand {
  if (Get-Command "gcloud.cmd" -ErrorAction SilentlyContinue) {
    return "gcloud.cmd"
  }
  if (Get-Command "gcloud" -ErrorAction SilentlyContinue) {
    return "gcloud"
  }
  throw "gcloud is not installed or is not on PATH"
}

$Gcloud = Get-GCloudCommand

function Assert-LastCommand {
  param([string]$Message)

  if ($LASTEXITCODE -ne 0) {
    throw $Message
  }
}

function Invoke-GCloud {
  param(
    [string[]]$Arguments,
    [string]$Message
  )

  & $Gcloud @Arguments
  Assert-LastCommand $Message
}

$Account = & $Gcloud auth list "--filter=status:ACTIVE" "--format=value(account)"
Assert-LastCommand "Unable to read active gcloud account"

Write-Host ""
Write-Host "EPYK Forge Google Cloud Bootstrap"
Write-Host ""
Write-Host ("Project       {0}" -f $ProjectId)
Write-Host ("Region        {0}" -f $Region)
Write-Host ("Account       {0}" -f (($Account | Out-String).Trim()))
Write-Host ""

Invoke-GCloud @(
  "services", "enable",
  "aiplatform.googleapis.com",
  "run.googleapis.com",
  "cloudbuild.googleapis.com",
  "pubsub.googleapis.com",
  "firestore.googleapis.com",
  "secretmanager.googleapis.com",
  "cloudtrace.googleapis.com",
  "logging.googleapis.com",
  "monitoring.googleapis.com",
  "artifactregistry.googleapis.com",
  "--project=$ProjectId"
) "Unable to enable required Google Cloud services"

$DatabaseNames = & $Gcloud firestore databases list "--project=$ProjectId" "--format=value(name)" 2>$null
if ($LASTEXITCODE -ne 0) {
  throw "Unable to list Firestore databases"
}

if (-not (($DatabaseNames | Out-String) -match '\(default\)')) {
  Invoke-GCloud @(
    "firestore", "databases", "create",
    "--project=$ProjectId",
    "--database=(default)",
    "--location=$Region",
    "--type=firestore-native"
  ) "Unable to create Firestore default database"
}

$TopicNames = @(
  "epyk-forge-factory-events",
  "epyk-forge-incident-events",
  "epyk-forge-agent-tasks",
  "epyk-forge-action-results",
  "epyk-forge-notifications"
)

$ExistingTopics = & $Gcloud pubsub topics list "--project=$ProjectId" "--format=value(name)"
Assert-LastCommand "Unable to list Pub/Sub topics"
$ExistingTopicsText = $ExistingTopics | Out-String

foreach ($Topic in $TopicNames) {
  $EscapedTopic = [regex]::Escape($Topic)
  if ($ExistingTopicsText -notmatch [regex]::Escape("/topics/$Topic") -and $ExistingTopicsText -notmatch "(^|[\r\n])$EscapedTopic($|[\r\n])") {
    Invoke-GCloud @(
      "pubsub", "topics", "create", $Topic,
      "--project=$ProjectId"
    ) "Unable to create Pub/Sub topic '$Topic'"
  }
}

Write-Host ""
Write-Host "Google Cloud project bootstrapped for EPYK Forge."

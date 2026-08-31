param(
  [string]$ProjectId = $env:GOOGLE_CLOUD_PROJECT,
  [string]$Region = $env:GOOGLE_CLOUD_LOCATION
)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
  $PSNativeCommandUseErrorActionPreference = $false
}

if ([string]::IsNullOrWhiteSpace($Region)) {
  $Region = "us-central1"
}

$Repo = "epyk-forge"
$ApiService = "forge-api"
$WebService = "forge-web"
$HostName = "$Region-docker.pkg.dev"

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

function Read-GCloud {
  param(
    [string[]]$Arguments,
    [string]$Message
  )

  $Output = & $Gcloud @Arguments
  Assert-LastCommand $Message
  return ($Output | Out-String).Trim()
}

function Get-CloudRunUrl {
  param(
    [string]$Service,
    [switch]$Required
  )

  $Output = & $Gcloud run services describe $Service "--project=$ProjectId" "--region=$Region" "--format=value(status.url)" 2>$null
  if ($LASTEXITCODE -ne 0) {
    if ($Required) {
      throw "Unable to describe Cloud Run service '$Service' in project '$ProjectId' region '$Region'"
    }
    return $null
  }

  $Url = ($Output | Out-String).Trim()
  if ([string]::IsNullOrWhiteSpace($Url)) {
    if ($Required) {
      throw "Cloud Run service '$Service' has no ready URL in project '$ProjectId' region '$Region'"
    }
    return $null
  }
  return $Url
}

function Assert-AbsoluteHttpUrl {
  param(
    [string]$Name,
    [string]$Url
  )

  if ($Url -notmatch '^https?://') {
    throw "$Name must be an absolute http(s) URL. Actual value: '$Url'"
  }
}

if ([string]::IsNullOrWhiteSpace($ProjectId)) {
  $ProjectId = Read-GCloud @("config", "get-value", "project") "Unable to read active gcloud project"
  if ([string]::IsNullOrWhiteSpace($ProjectId) -or $ProjectId -eq "(unset)") {
    throw "Set GOOGLE_CLOUD_PROJECT or configure an active gcloud project"
  }
  Write-Warning "GOOGLE_CLOUD_PROJECT is not set; using active gcloud project '$ProjectId'."
}

$ActiveProject = Read-GCloud @("config", "get-value", "project") "Unable to read active gcloud project"
if ($ActiveProject -and $ActiveProject -ne "(unset)" -and $ActiveProject -ne $ProjectId) {
  Write-Warning "Active gcloud project is '$ActiveProject'; deployment commands will explicitly use '$ProjectId'."
}

$Account = Read-GCloud @("auth", "list", "--filter=status:ACTIVE", "--format=value(account)") "Unable to read active gcloud account"
if ([string]::IsNullOrWhiteSpace($Account)) {
  throw "No active gcloud account. Run gcloud auth login first."
}

Write-Host ""
Write-Host "EPYK Forge Cloud Run Deployment"
Write-Host ""
Write-Host ("Project       {0}" -f $ProjectId)
Write-Host ("Region        {0}" -f $Region)
Write-Host ("Account       {0}" -f $Account)
Write-Host ("API service   {0}" -f $ApiService)
Write-Host ("Web service   {0}" -f $WebService)
Write-Host ""

$ApiImage = "$HostName/$ProjectId/$Repo/${ApiService}:latest"
$WebImage = "$HostName/$ProjectId/$Repo/${WebService}:latest"
$ExistingWebUrl = Get-CloudRunUrl $WebService

$Repositories = Read-GCloud @(
  "artifacts", "repositories", "list",
  "--project=$ProjectId",
  "--location=$Region",
  "--format=value(name)"
) "Unable to list Artifact Registry repositories"

$RepositoriesText = $Repositories | Out-String
$EscapedRepo = [regex]::Escape($Repo)
if ($RepositoriesText -notmatch [regex]::Escape("/repositories/$Repo") -and $RepositoriesText -notmatch "(^|[\r\n])$EscapedRepo($|[\r\n])") {
  Invoke-GCloud @(
    "artifacts", "repositories", "create", $Repo,
    "--project=$ProjectId",
    "--repository-format=docker",
    "--location=$Region",
    "--quiet"
  ) "Unable to create Artifact Registry repository '$Repo'"
}

Invoke-GCloud @(
  "builds", "submit",
  "--project=$ProjectId",
  "--config", "backend/cloudbuild.yaml",
  "--substitutions", "_IMAGE=$ApiImage",
  "."
) "API image build failed"

$ApiEnvVars = @(
  "FORGE_ENV=production",
  "FORGE_STORE_BACKEND=firestore",
  "FORGE_EVENT_BUS=pubsub",
  "FORGE_MODEL_PROVIDER=REAL_GEMINI",
  "FORGE_GEMINI_MODEL=gemini-3.5-flash",
  "GOOGLE_GENAI_USE_ENTERPRISE=True",
  "GOOGLE_CLOUD_PROJECT=$ProjectId",
  "GOOGLE_CLOUD_LOCATION=global",
  "FORGE_CLOUD_RUN_REGION=$Region"
)

if (-not [string]::IsNullOrWhiteSpace($ExistingWebUrl)) {
  $ApiEnvVars += "FORGE_WEB_ORIGIN=$ExistingWebUrl"
}

Invoke-GCloud @(
  "run", "deploy", $ApiService,
  "--project=$ProjectId",
  "--image", $ApiImage,
  "--region", $Region,
  "--allow-unauthenticated",
  "--set-env-vars", ($ApiEnvVars -join ","),
  "--quiet"
) "API service deployment failed"

Invoke-GCloud @(
  "run", "services", "add-iam-policy-binding", $ApiService,
  "--project=$ProjectId",
  "--region=$Region",
  "--member=allUsers",
  "--role=roles/run.invoker",
  "--quiet"
) "Unable to grant public invoker on forge-api"

$ApiUrl = Get-CloudRunUrl $ApiService -Required
Assert-AbsoluteHttpUrl "Forge API URL" $ApiUrl

Write-Host ""
Write-Host ("Forge Web API target: {0}" -f $ApiUrl)
Write-Host ""

Invoke-GCloud @(
  "builds", "submit",
  "--project=$ProjectId",
  "--config", "frontend/cloudbuild.yaml",
  "--substitutions", "_IMAGE=$WebImage,_VITE_FORGE_API_URL=$ApiUrl",
  "."
) "Web image build failed"

Invoke-GCloud @(
  "run", "deploy", $WebService,
  "--project=$ProjectId",
  "--image", $WebImage,
  "--region", $Region,
  "--allow-unauthenticated",
  "--quiet"
) "Web service deployment failed"

Invoke-GCloud @(
  "run", "services", "add-iam-policy-binding", $WebService,
  "--project=$ProjectId",
  "--region=$Region",
  "--member=allUsers",
  "--role=roles/run.invoker",
  "--quiet"
) "Unable to grant public invoker on forge-web"

$WebUrl = Get-CloudRunUrl $WebService -Required
Assert-AbsoluteHttpUrl "Forge Web URL" $WebUrl

Invoke-GCloud @(
  "run", "services", "update", $ApiService,
  "--project=$ProjectId",
  "--region", $Region,
  "--update-env-vars", "FORGE_WEB_ORIGIN=$WebUrl",
  "--quiet"
) "Unable to update forge-api CORS origin"

$ApiUrl = Get-CloudRunUrl $ApiService -Required

Write-Host ""
Write-Host ("API URL       {0}" -f $ApiUrl)
Write-Host ("Web URL       {0}" -f $WebUrl)
Write-Host ""

$SmokeScript = Join-Path $PSScriptRoot "smoke_cloud.ps1"
if (Test-Path $SmokeScript) {
  & $SmokeScript -ProjectId $ProjectId -Region $Region
  Assert-LastCommand "Cloud smoke test failed"
}

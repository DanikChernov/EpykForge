param(
  [string]$ProjectId = $env:GOOGLE_CLOUD_PROJECT,
  [string]$Region = $env:GOOGLE_CLOUD_LOCATION
)

$ErrorActionPreference = "Stop"
$script:Failures = 0
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
  $PSNativeCommandUseErrorActionPreference = $false
}

Add-Type -AssemblyName System.Net.Http

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

function Read-GCloud {
  param(
    [string[]]$Arguments,
    [string]$Message
  )

  $Output = & $Gcloud @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw $Message
  }
  return ($Output | Out-String).Trim()
}

if ([string]::IsNullOrWhiteSpace($ProjectId)) {
  $ProjectId = Read-GCloud @("config", "get-value", "project") "Unable to read active gcloud project"
  if ([string]::IsNullOrWhiteSpace($ProjectId) -or $ProjectId -eq "(unset)") {
    throw "Set GOOGLE_CLOUD_PROJECT or configure an active gcloud project"
  }
}

function Mark {
  param(
    [string]$Name,
    [bool]$Pass,
    [string]$Detail = ""
  )

  $Status = if ($Pass) { "PASS" } else { "FAIL" }
  Write-Host ("{0,-28} {1} {2}" -f $Name, $Status, $Detail)
  if (-not $Pass) {
    $script:Failures += 1
  }
}

function Get-CloudRunUrl {
  param([string]$Service)

  $Output = & $Gcloud run services describe $Service "--project=$ProjectId" "--region=$Region" "--format=value(status.url)" 2>$null
  if ($LASTEXITCODE -ne 0) {
    return $null
  }
  $Url = ($Output | Out-String).Trim()
  if ([string]::IsNullOrWhiteSpace($Url)) {
    return $null
  }
  return $Url
}

function Invoke-Http {
  param(
    [string]$Method,
    [string]$Url,
    [hashtable]$Headers = @{}
  )

  $Client = [System.Net.Http.HttpClient]::new()
  $Client.Timeout = [TimeSpan]::FromSeconds(25)
  $Request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Method.ToUpperInvariant()), $Url)

  foreach ($Key in $Headers.Keys) {
    [void]$Request.Headers.TryAddWithoutValidation($Key, [string]$Headers[$Key])
  }

  try {
    $Response = $Client.SendAsync($Request).GetAwaiter().GetResult()
    $Body = $Response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    $HeaderMap = @{}

    foreach ($Header in $Response.Headers.GetEnumerator()) {
      $HeaderMap[$Header.Key.ToLowerInvariant()] = ($Header.Value -join ",")
    }
    foreach ($Header in $Response.Content.Headers.GetEnumerator()) {
      $HeaderMap[$Header.Key.ToLowerInvariant()] = ($Header.Value -join ",")
    }

    $ContentType = ""
    if ($Response.Content.Headers.ContentType) {
      $ContentType = $Response.Content.Headers.ContentType.MediaType
    }

    return [pscustomobject]@{
      StatusCode = [int]$Response.StatusCode
      ContentType = $ContentType
      Body = $Body
      Headers = $HeaderMap
    }
  }
  finally {
    $Request.Dispose()
    $Client.Dispose()
  }
}

function Test-JsonEndpoint {
  param(
    [string]$Name,
    [string]$Url
  )

  try {
    $Response = Invoke-Http "GET" $Url
    $StatusOk = $Response.StatusCode -ge 200 -and $Response.StatusCode -lt 300
    $JsonContent = $Response.ContentType -like "*application/json*"
    $JsonParsed = $false
    if ($JsonContent) {
      $null = $Response.Body | ConvertFrom-Json
      $JsonParsed = $true
    }
    Mark $Name ($StatusOk -and $JsonContent -and $JsonParsed) ("HTTP {0} {1}" -f $Response.StatusCode, $Response.ContentType)
    return $Response
  }
  catch {
    Mark $Name $false $_.Exception.Message
    return $null
  }
}

Write-Host ""
Write-Host "EPYK Forge Cloud Smoke Test"
Write-Host ""
Write-Host ("Project       {0}" -f $ProjectId)
Write-Host ("Region        {0}" -f $Region)
Write-Host ""

$ApiUrl = Get-CloudRunUrl "forge-api"
$WebUrl = Get-CloudRunUrl "forge-web"

Mark "forge-api" (-not [string]::IsNullOrWhiteSpace($ApiUrl)) $(if ($ApiUrl) { "FOUND $ApiUrl" } else { "NOT FOUND" })
Mark "forge-web" (-not [string]::IsNullOrWhiteSpace($WebUrl)) $(if ($WebUrl) { "FOUND $WebUrl" } else { "NOT FOUND" })
Write-Host ""

if ([string]::IsNullOrWhiteSpace($ApiUrl) -or [string]::IsNullOrWhiteSpace($WebUrl)) {
  Write-Host ""
  Write-Host "RESULT"
  Write-Host "FAIL"
  exit 1
}

$HealthResponse = Test-JsonEndpoint "API /health" "$ApiUrl/health"
$ReadyResponse = Test-JsonEndpoint "API /ready" "$ApiUrl/ready"
$SystemResponse = Test-JsonEndpoint "API /api/system/info" "$ApiUrl/api/system/info"

if ($SystemResponse) {
  Mark "API content type" ($SystemResponse.ContentType -like "*application/json*") $SystemResponse.ContentType
}

try {
  $WebResponse = Invoke-Http "GET" $WebUrl
  Mark "Web root" ($WebResponse.StatusCode -eq 200 -and $WebResponse.ContentType -like "*text/html*") ("HTTP {0} {1}" -f $WebResponse.StatusCode, $WebResponse.ContentType)
}
catch {
  $WebResponse = $null
  Mark "Web root" $false $_.Exception.Message
}

if ($WebResponse) {
  $AssetMatch = [regex]::Match($WebResponse.Body, 'src="([^"]+\.js)"')
  if ($AssetMatch.Success) {
    $AssetPath = $AssetMatch.Groups[1].Value
    $AssetUrl = if ($AssetPath -match '^https?://') { $AssetPath } else { "$WebUrl$AssetPath" }
    try {
      $BundleResponse = Invoke-Http "GET" $AssetUrl
      Mark "Frontend API target" ($BundleResponse.Body.Contains($ApiUrl)) $ApiUrl
    }
    catch {
      Mark "Frontend API target" $false $_.Exception.Message
    }
  }
  else {
    Mark "Frontend API target" $false "Unable to find frontend JS asset"
  }
}

try {
  $CorsResponse = Invoke-Http "OPTIONS" "$ApiUrl/api/admin/setup/status" @{
    "Origin" = $WebUrl
    "Access-Control-Request-Method" = "GET"
    "Access-Control-Request-Headers" = "x-admin-pin,content-type"
  }
  $AllowOrigin = $CorsResponse.Headers["access-control-allow-origin"]
  Mark "CORS" ($CorsResponse.StatusCode -eq 200 -and $AllowOrigin -eq $WebUrl) ("allow-origin {0}" -f $AllowOrigin)
}
catch {
  Mark "CORS" $false $_.Exception.Message
}

Write-Host ""
Write-Host "RESULT"
if ($script:Failures -eq 0) {
  Write-Host "PASS"
  exit 0
}

Write-Host "FAIL"
exit 1

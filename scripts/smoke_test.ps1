$ErrorActionPreference = "Stop"

$BaseUrl = if ($env:FORGE_API_URL) { $env:FORGE_API_URL } else { "http://localhost:8080" }
Invoke-RestMethod "$BaseUrl/health"
Invoke-RestMethod "$BaseUrl/api/demo/reset" -Method Post
Invoke-RestMethod "$BaseUrl/api/demo/start" -Method Post -ContentType "application/json" -Body '{"sync":true,"speed":99}'
Invoke-RestMethod "$BaseUrl/api/incidents/INC-1042"

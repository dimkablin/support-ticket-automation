param([switch]$ValidateOnly)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

function Invoke-Checked([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
}

function Wait-Http([string]$Name, [string]$Url, [int]$TimeoutSeconds) {
    Write-Host "Waiting for ${Name}: $Url"
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $nextReport = 30
    while ($watch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        & curl.exe --fail --silent --show-error --max-time 5 --output NUL $Url 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "$Name is ready"
            return
        }
        if ($watch.Elapsed.TotalSeconds -ge $nextReport) {
            Write-Host "$Name is still starting ($([int]$watch.Elapsed.TotalSeconds) s)"
            $nextReport += 30
        }
        Start-Sleep -Seconds 5
    }
    throw "$Name was not ready after $TimeoutSeconds seconds"
}

foreach ($command in @("docker", "uv", "curl.exe")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Command not found: $command"
    }
}
if (-not (Test-Path ".env")) {
    throw ".env not found. Copy .env.example and fill in its values."
}

$config = @{}
foreach ($line in Get-Content ".env") {
    if ($line -match "^([A-Za-z_][A-Za-z0-9_]*)=(.*)$") {
        $config[$Matches[1]] = $Matches[2]
    }
}
$required = @(
    "QDRANT_URL", "QDRANT_API_KEY", "BGE_M3_BASE_URL",
    "LANGFUSE_BASE_URL", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY",
    "LITELLM_URL", "LITELLM_API_KEY", "AUDIT_POSTGRES_PASSWORD", "APP_PORT"
)
$missing = @($required | Where-Object {
    -not $config.ContainsKey($_) -or [string]::IsNullOrWhiteSpace($config[$_])
})
if ($missing) {
    throw "Missing .env values: $($missing -join ', ')"
}

$composeFiles = @(
    "docker-compose.qdrant.yml",
    "docker-compose.bge-m3.yml",
    "docker-compose.langfuse.yml",
    "docker-compose.yml"
)
foreach ($file in $composeFiles) {
    Invoke-Checked "docker" @("compose", "--env-file", ".env", "-f", $file, "config", "--quiet")
}
if ($ValidateOnly) {
    Write-Host "Startup configuration is valid"
    exit 0
}

Invoke-Checked "uv" @("sync", "--extra", "dev")
Invoke-Checked "docker" @("compose", "--env-file", ".env", "-f", "docker-compose.qdrant.yml", "up", "-d")
Invoke-Checked "docker" @("compose", "--env-file", ".env", "-f", "docker-compose.langfuse.yml", "up", "-d")
Invoke-Checked "docker" @("compose", "--env-file", ".env", "-f", "docker-compose.bge-m3.yml", "up", "-d")

Wait-Http "Qdrant" "$($config['QDRANT_URL'])/healthz" 120
Wait-Http "Langfuse" "$($config['LANGFUSE_BASE_URL'])/api/public/health" 300
$bgeHealth = $config["BGE_M3_BASE_URL"] -replace "/v1/?$", "/health"
Wait-Http "RuBERT Tiny 2" $bgeHealth 1800

Invoke-Checked "uv" @("run", "python", "scripts/index_kb.py")
Invoke-Checked "docker" @("compose", "--env-file", ".env", "-f", "docker-compose.yml", "up", "--build", "-d")
Wait-Http "Streamlit" "http://localhost:$($config['APP_PORT'])/_stcore/health" 180

Write-Host "Ready: http://localhost:$($config['APP_PORT'])"
Write-Host "Langfuse: $($config['LANGFUSE_BASE_URL'])"
Write-Host "Qdrant: $($config['QDRANT_URL'])/dashboard"

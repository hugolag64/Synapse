[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$SynapseUrl = "https://synapse.home.arpa"
)

$ErrorActionPreference = "Stop"

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$agent = Join-Path $RepoRoot "scripts\ednpro\qcm_capture_agent.py"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python du venv introuvable : $python"
}
if (-not (Test-Path -LiteralPath $agent)) {
    throw "Agent EDNpro introuvable : $agent"
}

$secureToken = Read-Host "Token EDNPRO_CAPTURE_TOKEN" -AsSecureString
$tokenPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPtr)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPtr)
}
if ([string]::IsNullOrWhiteSpace($token)) {
    throw "Le token ne peut pas être vide."
}

$configDir = Join-Path $env:APPDATA "Synapse"
$configPath = Join-Path $configDir "ednpro-capture-agent.json"
$profileDir = Join-Path $configDir "ednpro-chrome"
New-Item -ItemType Directory -Force -Path $configDir, $profileDir | Out-Null

$config = [ordered]@{
    synapse_url = $SynapseUrl
    token = $token
    profile_dir = $profileDir
    listen_host = "127.0.0.1"
    listen_port = 8876
    poll_seconds = 0.75
}
$json = $config | ConvertTo-Json -Compress
[IO.File]::WriteAllText($configPath, $json, [Text.UTF8Encoding]::new($false))

$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$acl = Get-Acl -LiteralPath $configPath
$acl.SetAccessRuleProtection($true, $false)
$acl.SetAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($currentUser, "FullControl", "Allow")))
Set-Acl -LiteralPath $configPath -AclObject $acl

$taskName = "Synapse EDNpro Capture Agent"
$arguments = '-u "' + $agent + '" --config "' + $configPath + '"'
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 2

try {
    $health = Invoke-WebRequest "http://127.0.0.1:8876/health" -UseBasicParsing
    Write-Host "Agent EDNpro installé et démarré."
    Write-Host $health.Content
}
catch {
    Write-Warning "La tâche est installée mais l'agent ne répond pas encore : $($_.Exception.Message)"
}


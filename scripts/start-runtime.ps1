#requires -Version 5.1
[CmdletBinding()]
param(
  [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
  [switch]$StartEdge,
  [switch]$NoFrontend,
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173,
  [int]$CdpPort = 9222,
  [int]$WaitSeconds = 30
)
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$RuntimeRoot = Join-Path $ProjectRoot ".local\runtime"
$PidRoot = Join-Path $RuntimeRoot "pids"
$LogRoot = Join-Path $RuntimeRoot "logs"
$CdpEndpoint = "http://127.0.0.1:$CdpPort"
if (-not (Test-Path -LiteralPath $Python)) { throw "Python runtime not found: $Python" }
New-Item -ItemType Directory -Force -Path $PidRoot,$LogRoot | Out-Null

function Test-Port([int]$Port) { [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1) }
function Test-Http([string]$Uri) { try { $null=Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2; $true } catch { $false } }
function Wait-Http([string]$Uri,[int]$Seconds) {
  for($i=0;$i -lt [Math]::Max(1,$Seconds*2);$i++){ if(Test-Http $Uri){return $true}; Start-Sleep -Milliseconds 500 }; $false
}
function Get-Cmd([int]$ProcessId) { try { (Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop).CommandLine } catch { $null } }
function Find-Token([string]$Token) {
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine.IndexOf($ProjectRoot,[StringComparison]::OrdinalIgnoreCase) -ge 0 -and $_.CommandLine.IndexOf($Token,[StringComparison]::OrdinalIgnoreCase) -ge 0
  } | Select-Object -First 1
}
function Read-Record([string]$Name,[string]$Token) {
  $path=Join-Path $PidRoot "$Name.json"; if(-not(Test-Path -LiteralPath $path)){return $null}
  try {
    $m=Get-Content -Raw -LiteralPath $path|ConvertFrom-Json; $cmd=Get-Cmd ([int]$m.process_id)
    if($cmd -and $cmd.IndexOf($ProjectRoot,[StringComparison]::OrdinalIgnoreCase) -ge 0 -and $cmd.IndexOf($Token,[StringComparison]::OrdinalIgnoreCase) -ge 0){return [PSCustomObject]@{process_id=[int]$m.process_id;state="ALREADY_RUNNING"}}
  } catch {}
  Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue; $null
}
function Save-Record([string]$Name,[int]$ProcessId,[string]$Command) {
  [PSCustomObject]@{schema_version="local-runtime-v1";service=$Name;process_id=$ProcessId;command=$Command;project_root=$ProjectRoot;started_at=[DateTime]::UtcNow.ToString("o");owned_by_runtime=$true} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PidRoot "$Name.json") -Encoding UTF8
}
function Rotate-Log([string]$Path) {
  if(-not(Test-Path -LiteralPath $Path)){return}; if((Get-Item -LiteralPath $Path).Length -lt 5MB){return}
  Remove-Item -LiteralPath "$Path.3" -Force -ErrorAction SilentlyContinue
  if(Test-Path -LiteralPath "$Path.2"){Move-Item "$Path.2" "$Path.3" -Force}
  if(Test-Path -LiteralPath "$Path.1"){Move-Item "$Path.1" "$Path.2" -Force}
  Move-Item $Path "$Path.1" -Force
}
function Start-ServiceProcess([string]$Name,[string]$Token,[string]$File,[string[]]$Arguments,[string]$WorkingDirectory=$ProjectRoot) {
  $known=Read-Record $Name $Token; if($known){return $known}
  $running=Find-Token $Token; if($running){return [PSCustomObject]@{process_id=[int]$running.ProcessId;state="ALREADY_RUNNING"}}
  $out=Join-Path $LogRoot "$Name.out.log"; $err=Join-Path $LogRoot "$Name.err.log"; Rotate-Log $out; Rotate-Log $err
  $p=Start-Process -FilePath $File -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
  Save-Record $Name ([int]$p.Id) (($File+" "+($Arguments -join " "))); Start-Sleep -Milliseconds 500
  if($p.HasExited){throw "$Name exited immediately with code $($p.ExitCode). See $err"}
  [PSCustomObject]@{process_id=[int]$p.Id;state="STARTED"}
}
function Test-Cdp { try { $null=Invoke-RestMethod "$CdpEndpoint/json/version" -TimeoutSec 2; $true } catch {$false} }
function Get-ProfilePath {
  $path=Join-Path $ProjectRoot ".local\edge-cdp-profile"
  New-Item -ItemType Directory -Force $path|Out-Null
  (Resolve-Path $path).Path
}

if(-not(Test-Port 5432)){throw "DATABASE_UNAVAILABLE: PostgreSQL is not listening on 127.0.0.1:5432."}
$cdpState="ACTION_REQUIRED_CDP_UNAVAILABLE"
if(Test-Cdp){$cdpState="AVAILABLE"}else{
  $edgeRunning=[bool](Get-Process msedge -ErrorAction SilentlyContinue)
  if(-not $edgeRunning -and $StartEdge){
    $edge=@("C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe","C:\Program Files\Microsoft\Edge\Application\msedge.exe")|Where-Object{Test-Path $_}|Select-Object -First 1
    if(-not $edge){$edge=(Get-Command msedge.exe -ErrorAction SilentlyContinue).Source}
    if($edge){$profile=Get-ProfilePath; Start-Process $edge -ArgumentList @("--remote-debugging-port=$CdpPort","--remote-debugging-address=127.0.0.1","--user-data-dir=$profile","--profile-directory=Default","--no-first-run","--no-default-browser-check","https://xueqiu.com/") -WorkingDirectory (Split-Path -Parent $edge);$cdpState=if(Wait-Http "$CdpEndpoint/json/version" $WaitSeconds){"AVAILABLE"}else{"ACTION_REQUIRED_CDP_START_FAILED"}}else{$cdpState="ACTION_REQUIRED_EDGE_NOT_FOUND"}
  }elseif($edgeRunning){$cdpState="ACTION_REQUIRED_EDGE_ALREADY_RUNNING_WITHOUT_CDP"}
}

$backend=if(Test-Http "http://127.0.0.1:$BackendPort/health"){[PSCustomObject]@{state="ALREADY_RUNNING";process_id=$null}}elseif(Test-Port $BackendPort){throw "BACKEND_PORT_OCCUPIED: port $BackendPort is listening but /health is unavailable."}else{Start-ServiceProcess "backend" "backend.app.main:app" $Python @("-m","uvicorn","backend.app.main:app","--host","127.0.0.1","--port","$BackendPort")}
if(-not(Wait-Http "http://127.0.0.1:$BackendPort/health" $WaitSeconds)){throw "BACKEND_NOT_READY: /health did not become available."}
$scheduler=Start-ServiceProcess "scheduler" "operations.scheduler" $Python @("-m","operations.scheduler","--cdp-endpoint",$CdpEndpoint)
if(-not(Get-Cmd ([int]$scheduler.process_id))){throw "SCHEDULER_NOT_RUNNING: scheduler process is not alive."}
if($NoFrontend){$frontend=[PSCustomObject]@{state="NOT_REQUESTED";process_id=$null}}else{
  $npm=(Get-Command npm.cmd -ErrorAction SilentlyContinue).Source;if(-not $npm){throw "FRONTEND_RUNTIME_NOT_FOUND: npm.cmd is unavailable."}
  $frontend=if(Test-Http "http://127.0.0.1:$FrontendPort/"){[PSCustomObject]@{state="ALREADY_RUNNING";process_id=$null}}elseif(Test-Port $FrontendPort){throw "FRONTEND_PORT_OCCUPIED: port $FrontendPort is listening but Vite is unavailable."}else{Start-ServiceProcess -Name "frontend" -Token "vite" -File $npm -Arguments @("run","dev","--","--host","127.0.0.1","--port","$FrontendPort") -WorkingDirectory (Join-Path $ProjectRoot "frontend")}
  if(-not(Wait-Http "http://127.0.0.1:$FrontendPort/" $WaitSeconds)){throw "FRONTEND_NOT_READY: Vite did not become available."}
}
try{$status=Invoke-RestMethod "http://127.0.0.1:$BackendPort/api/operations/status" -TimeoutSec 3}catch{$status=[PSCustomObject]@{status="UNKNOWN";error="STATUS_API_UNAVAILABLE"}}
[ordered]@{schema_version="local-runtime-v1";project_root=$ProjectRoot;postgres="AVAILABLE";cdp=$cdpState;backend=$backend;scheduler=$scheduler;frontend=$frontend;operational_status=$status;log_root=$LogRoot;started_at=[DateTime]::UtcNow.ToString("o")}|ConvertTo-Json -Depth 6
exit 0

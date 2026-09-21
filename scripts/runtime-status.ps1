#requires -Version 5.1
[CmdletBinding()]
param([string]$ProjectRoot=(Split-Path -Parent $PSScriptRoot),[int]$BackendPort=8000,[int]$FrontendPort=5173,[int]$CdpPort=9222)
$ErrorActionPreference="SilentlyContinue";$ProjectRoot=(Resolve-Path $ProjectRoot).Path;$PidRoot=Join-Path $ProjectRoot ".local\runtime\pids"
function Port([int]$p){[bool](Get-NetTCPConnection -State Listen -LocalPort $p|Select-Object -First 1)}
function Cmd([int]$p){try{(Get-CimInstance Win32_Process -Filter "ProcessId=$p").CommandLine}catch{$null}}
function Svc([string]$n,[string]$t){
 $path=Join-Path $PidRoot "$n.json";if(Test-Path $path){try{$m=Get-Content -Raw $path|ConvertFrom-Json;$c=Cmd ([int]$m.process_id);if($c -and $c.IndexOf($ProjectRoot,[StringComparison]::OrdinalIgnoreCase)-ge 0 -and $c.IndexOf($t,[StringComparison]::OrdinalIgnoreCase)-ge 0){return [PSCustomObject]@{state="RUNNING";process_id=[int]$m.process_id}}}catch{}}
 $p=Get-CimInstance Win32_Process|Where-Object{$_.CommandLine -and $_.CommandLine.IndexOf($ProjectRoot,[StringComparison]::OrdinalIgnoreCase)-ge 0 -and $_.CommandLine.IndexOf($t,[StringComparison]::OrdinalIgnoreCase)-ge 0}|Select-Object -First 1
 if($p){[PSCustomObject]@{state="RUNNING_UNTRACKED";process_id=[int]$p.ProcessId}}else{[PSCustomObject]@{state="NOT_RUNNING";process_id=$null}}
}
function Json([string]$u){try{Invoke-RestMethod $u -TimeoutSec 3}catch{$null}}
$cdp=Json "http://127.0.0.1:$CdpPort/json/version";$health=Json "http://127.0.0.1:$BackendPort/health";$status=Json "http://127.0.0.1:$BackendPort/api/operations/status";$front=try{$null=Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$FrontendPort/" -TimeoutSec 3;$true}catch{$false}
[ordered]@{schema_version="local-runtime-v1";project_root=$ProjectRoot;postgres=if(Port 5432){"AVAILABLE"}else{"UNAVAILABLE"};cdp=if($cdp){[PSCustomObject]@{state="AVAILABLE";browser=$cdp.Browser}}else{[PSCustomObject]@{state="ACTION_REQUIRED"}};backend=if($health){[PSCustomObject]@{state="HEALTHY";response=$health}}else{[PSCustomObject]@{state="NOT_READY"}};scheduler=Svc "scheduler" "operations.scheduler";frontend=if($front){"AVAILABLE"}else{"NOT_READY"};operational_status=$status;checked_at=[DateTime]::UtcNow.ToString("o")}|ConvertTo-Json -Depth 7
if(-not$health -or $front -eq $false -or (Svc "scheduler" "operations.scheduler").state -eq "NOT_RUNNING"){exit 2};if(-not$cdp){exit 3};exit 0

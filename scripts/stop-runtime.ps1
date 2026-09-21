#requires -Version 5.1
[CmdletBinding()]
param([string]$ProjectRoot=(Split-Path -Parent $PSScriptRoot),[switch]$StopEdge)
$ErrorActionPreference="Stop"
$ProjectRoot=(Resolve-Path $ProjectRoot).Path
$PidRoot=Join-Path $ProjectRoot ".local\runtime\pids"
$tokens=[ordered]@{backend="backend.app.main:app";scheduler="operations.scheduler";frontend="vite"}

function Cmd([int]$ProcessId){try{(Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop).CommandLine}catch{$null}}
function Tree([int]$Root){
  $all=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  $found=New-Object System.Collections.Generic.List[int]
  $q=New-Object System.Collections.Generic.Queue[int]
  $q.Enqueue($Root)
  while($q.Count -gt 0){
    $cur=$q.Dequeue()
    if($found.Contains($cur)){continue}
    $found.Add($cur)
    foreach($child in $all|Where-Object{$_.ParentProcessId -eq $cur}){$q.Enqueue([int]$child.ProcessId)}
  }
  $found
}
function Stop-Owned([int]$ProcessId,[string]$Token,[bool]$Recorded){
  $cmd=Cmd $ProcessId
  $projectMatch=$cmd -and $cmd.IndexOf($ProjectRoot,[StringComparison]::OrdinalIgnoreCase)-ge 0
  $tokenMatch=$cmd -and $cmd.IndexOf($Token,[StringComparison]::OrdinalIgnoreCase)-ge 0
  if(-not $cmd -or -not $tokenMatch -or (-not $Recorded -and -not $projectMatch)){return "SKIPPED_PID_NOT_OWNED"}
  foreach($child in (Tree $ProcessId|Sort-Object -Descending)){Stop-Process -Id $child -Force -ErrorAction SilentlyContinue}
  "STOPPED"
}
$result=[ordered]@{}
foreach($service in $tokens.Keys){
  $path=Join-Path $PidRoot "$service.json"
  $state="NOT_RUNNING"
  if(Test-Path $path){
    try{$m=Get-Content -Raw $path|ConvertFrom-Json;$state=Stop-Owned ([int]$m.process_id) $tokens[$service] $true}catch{$state="STALE_METADATA"}
    Remove-Item $path -Force -ErrorAction SilentlyContinue
  }else{
    $candidate=$null
    if($service -eq "frontend"){
      $owner=(Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue|Select-Object -First 1).OwningProcess
      if($owner){$candidate=Get-CimInstance Win32_Process -Filter "ProcessId=$owner" -ErrorAction SilentlyContinue}
    }else{
      $candidate=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|Where-Object{$_.CommandLine -and $_.CommandLine.IndexOf($ProjectRoot,[StringComparison]::OrdinalIgnoreCase)-ge 0 -and $_.CommandLine.IndexOf($tokens[$service],[StringComparison]::OrdinalIgnoreCase)-ge 0}|Select-Object -First 1
    }
    if($candidate){$state=Stop-Owned ([int]$candidate.ProcessId) $tokens[$service] $false}
  }
  $result[$service]=$state
}
if($StopEdge){$result.edge="NOT_RUNTIME_OWNED"}
$result|ConvertTo-Json -Depth 4
exit 0
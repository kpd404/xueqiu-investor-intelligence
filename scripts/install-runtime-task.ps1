#requires -Version 5.1
[CmdletBinding()]
param([string]$ProjectRoot=(Split-Path -Parent $PSScriptRoot),[string]$TaskName="SnowBall Local Runtime",[switch]$Uninstall)
$ErrorActionPreference="Stop";$ProjectRoot=(Resolve-Path $ProjectRoot).Path;$scriptPath=Join-Path $ProjectRoot "scripts\start-runtime.ps1";$user="$env:USERDOMAIN\$env:USERNAME"
if($Uninstall){Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue;Write-Output "UNINSTALLED $TaskName";exit 0}
$pwsh=(Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source;if(-not$pwsh){$pwsh=(Get-Command powershell.exe -ErrorAction Stop).Source}
$argument='-NoProfile -ExecutionPolicy Bypass -File "'+$scriptPath+'" -StartEdge'
$action=New-ScheduledTaskAction -Execute $pwsh -Argument $argument;$trigger=New-ScheduledTaskTrigger -AtLogOn -User $user;$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Days 1);$principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force|Out-Null;Write-Output "INSTALLED $TaskName for interactive user logon"

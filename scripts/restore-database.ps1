#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$BackupPath,
    [Parameter(Mandatory=$true)][string]$TargetDatabase,
    [string]$ManifestPath = "",
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference="Stop"
$ProjectRoot=(Resolve-Path $ProjectRoot).Path
$Python=Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Alembic=Join-Path $ProjectRoot ".venv\Scripts\alembic.exe"
if(-not(Test-Path $Python)){throw "Python runtime not found"}
if(-not(Test-Path $BackupPath)){throw "BACKUP_NOT_FOUND"}
$BackupPath=(Resolve-Path $BackupPath).Path
if((Get-Item $BackupPath).Length-le 0){throw "BACKUP_EMPTY"}
if($TargetDatabase -notmatch "^snowball_restore_verify_[A-Za-z0-9_]+$"){throw "RESTORE_TARGET_INVALID"}
if(-not $ManifestPath){$ManifestPath=[IO.Path]::ChangeExtension($BackupPath,".json")}
if(-not(Test-Path $ManifestPath)){throw "MANIFEST_NOT_FOUND"}
function Tool([string]$n){$c=Get-Command "$n.exe" -ErrorAction SilentlyContinue;if($c){return $c.Source};$x=Get-ChildItem -Path "C:\Program Files\PostgreSQL\*\bin\$n.exe" -File -ErrorAction SilentlyContinue|Sort-Object FullName -Descending|Select-Object -First 1;if($x){$x.FullName}else{throw "REQUIRED_TOOL_NOT_FOUND: $n.exe"}}
function DbUrl{$v=[Environment]::GetEnvironmentVariable("DATABASE_URL");if(-not $v){$l=Get-Content (Join-Path $ProjectRoot ".env")|Where-Object{$_ -match "^DATABASE_URL="}|Select-Object -First 1;if($l -match "^DATABASE_URL=(.*)$"){$v=$Matches[1].Trim()}};if(-not $v){throw "DATABASE_URL is not configured"};$v}
function ParseDb([string]$v){$u=[Uri]($v -replace "^postgresql\+[^:]+://","postgresql://");$ui=[Uri]::UnescapeDataString($u.UserInfo);$p=$ui.Split(":",2);if($p.Count-lt 2){throw "DATABASE_URL must include user and password"};[PSCustomObject]@{Host=$u.Host;Port=if($u.Port-gt 0){$u.Port}else{5432};Database=$u.AbsolutePath.Trim("/");User=$p[0];Password=$p[1]}}
function SetPg($c){$keys=@("PGHOST","PGPORT","PGDATABASE","PGUSER","PGPASSWORD");$old=@{};foreach($k in $keys){$old[$k]=[Environment]::GetEnvironmentVariable($k)};$env:PGHOST=$c.Host;$env:PGPORT="$($c.Port)";$env:PGDATABASE=$c.Database;$env:PGUSER=$c.User;$env:PGPASSWORD=$c.Password;$old}
function RestorePg($old){foreach($k in $old.Keys){[Environment]::SetEnvironmentVariable($k,$old[$k])}}
$restore=Tool "pg_restore";$createdb=Tool "createdb";$psql=Tool "psql";$c=ParseDb (DbUrl)
if($TargetDatabase -eq $c.Database){throw "LIVE_DATABASE_REFUSAL: restore target equals live database"}
$old=SetPg $c
try{
 & $restore --list $BackupPath|Out-Null;if($LASTEXITCODE-ne 0){throw "BACKUP_LIST_INVALID"}
$q="SELECT 1 FROM pg_database WHERE datname = '$TargetDatabase'"
$exists=(& $psql --host=$($c.Host) --port=$($c.Port) --username=$($c.User) --dbname=postgres --tuples-only --no-align --quiet --command=$q|Out-String).Trim()
if($LASTEXITCODE-ne 0){throw "RESTORE_TARGET_PROBE_FAILED"}
if($exists -eq "1"){throw "RESTORE_TARGET_ALREADY_EXISTS"}
& $createdb --host=$($c.Host) --port=$($c.Port) --username=$($c.User) --owner=$($c.User) $TargetDatabase;if($LASTEXITCODE-ne 0){throw "CREATE_RESTORE_DATABASE_FAILED"}
& $restore --exit-on-error --no-owner --dbname=$TargetDatabase --host=$($c.Host) --port=$($c.Port) --username=$($c.User) $BackupPath;if($LASTEXITCODE-ne 0){throw "PG_RESTORE_FAILED"}
$env:DATABASE_URL="postgresql+psycopg://$($c.User)@$($c.Host):$($c.Port)/$TargetDatabase"
& $Alembic check|Out-Null;if($LASTEXITCODE-ne 0){throw "ALEMBIC_RESTORE_CHECK_FAILED"}
$verification=& $Python -m scripts.verify_database_restore --manifest $ManifestPath --expected-database $TargetDatabase
if($LASTEXITCODE-ne 0){throw ("RESTORE_VERIFICATION_FAILED: "+$verification)}
Write-Output $verification
Write-Output "RESTORE_TARGET_RETAINED=$TargetDatabase"
}finally{RestorePg $old}
exit 0




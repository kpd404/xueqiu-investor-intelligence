#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$OutputDirectory = ""
)
$ErrorActionPreference="Stop"
$ProjectRoot=(Resolve-Path $ProjectRoot).Path
$Python=Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if(-not(Test-Path $Python)){throw "Python runtime not found"}
if(-not $OutputDirectory){$OutputDirectory=Join-Path $ProjectRoot ".local\backups"}
New-Item -ItemType Directory -Force $OutputDirectory|Out-Null
$OutputDirectory=(Resolve-Path $OutputDirectory).Path
function Tool([string]$n){
 $c=Get-Command "$n.exe" -ErrorAction SilentlyContinue;if($c){return $c.Source}
 $x=Get-ChildItem -Path "C:\Program Files\PostgreSQL\*\bin\$n.exe" -File -ErrorAction SilentlyContinue|Sort-Object FullName -Descending|Select-Object -First 1
 if($x){return $x.FullName};throw "REQUIRED_TOOL_NOT_FOUND: $n.exe"
}
function DbUrl{
 $v=[Environment]::GetEnvironmentVariable("DATABASE_URL")
 if(-not $v){$l=Get-Content (Join-Path $ProjectRoot ".env")|Where-Object{$_ -match "^DATABASE_URL="}|Select-Object -First 1;if($l -match "^DATABASE_URL=(.*)$"){$v=$Matches[1].Trim()}}
 if(-not $v){throw "DATABASE_URL is not configured"};$v
}
function ParseDb([string]$v){
 $u=[Uri]($v -replace "^postgresql\+[^:]+://","postgresql://");$ui=[Uri]::UnescapeDataString($u.UserInfo);$p=$ui.Split(":",2)
 if($p.Count-lt 2){throw "DATABASE_URL must include user and password"}
 [PSCustomObject]@{Host=$u.Host;Port=if($u.Port-gt 0){$u.Port}else{5432};Database=$u.AbsolutePath.Trim("/");User=$p[0];Password=$p[1]}
}
function SetPg($c){
 $keys=@("PGHOST","PGPORT","PGDATABASE","PGUSER","PGPASSWORD");$old=@{}
 foreach($k in $keys){$old[$k]=[Environment]::GetEnvironmentVariable($k)}
 $env:PGHOST=$c.Host;$env:PGPORT="$($c.Port)";$env:PGDATABASE=$c.Database;$env:PGUSER=$c.User;$env:PGPASSWORD=$c.Password;$old
}
function RestorePg($old){foreach($k in $old.Keys){[Environment]::SetEnvironmentVariable($k,$old[$k])}}
$dump=Tool "pg_dump";$restore=Tool "pg_restore";$c=ParseDb (DbUrl)
$stamp=Get-Date -Format "yyyyMMdd-HHmmss";$dumpPath=Join-Path $OutputDirectory "snowball-$stamp.dump";$manifestPath=[IO.Path]::ChangeExtension($dumpPath,".json")
$old=SetPg $c
try{
 $manifestText=& $Python -m scripts.database_snapshot_manifest;if($LASTEXITCODE-ne 0){throw "MANIFEST_FAILED"}
 & $dump --format=custom --file=$dumpPath --host=$($c.Host) --port=$($c.Port) --username=$($c.User) --dbname=$($c.Database) --no-owner --no-privileges
 if($LASTEXITCODE-ne 0){throw "PG_DUMP_FAILED"}
 if(-not(Test-Path $dumpPath)-or(Get-Item $dumpPath).Length-le 0){throw "BACKUP_ARTIFACT_INVALID"}
 & $restore --list $dumpPath|Out-Null;if($LASTEXITCODE-ne 0){throw "PG_RESTORE_LIST_FAILED"}
 $m=$manifestText|ConvertFrom-Json;$h=Get-FileHash -Algorithm SHA256 $dumpPath
 $m|Add-Member backup_file ([IO.Path]::GetFileName($dumpPath)) -Force
 $m|Add-Member backup_size_bytes ([int64](Get-Item $dumpPath).Length) -Force
 $m|Add-Member backup_sha256 $h.Hash.ToLowerInvariant() -Force
 $m|ConvertTo-Json -Depth 10|Set-Content $manifestPath -Encoding UTF8
 [PSCustomObject]@{status="SUCCESS";backup_path=$dumpPath;manifest_path=$manifestPath;size_bytes=$m.backup_size_bytes;sha256=$m.backup_sha256;database=$m.database;migration_head=$m.migration_head}|ConvertTo-Json -Depth 5
}finally{RestorePg $old}
exit 0


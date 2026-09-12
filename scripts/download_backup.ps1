$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$backupDir = Join-Path $projectDir 'backups'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$backupFile = Join-Path $backupDir 'AdventureWorks2016.bak'
if (Test-Path -LiteralPath $backupFile) {
    Write-Host 'Backup já existe. Mantido sem sobrescrever.'
    exit 0
}
$downloadFile = Join-Path $backupDir 'AdventureWorks2016.bak.partial'
Invoke-WebRequest -Uri 'https://github.com/Microsoft/sql-server-samples/releases/download/adventureworks/AdventureWorks2016.bak' -OutFile $downloadFile
Move-Item -LiteralPath $downloadFile -Destination $backupFile
Get-FileHash -LiteralPath $backupFile -Algorithm SHA256

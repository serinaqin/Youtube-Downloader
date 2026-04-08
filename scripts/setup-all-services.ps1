#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Installs YoutubeDownloader, NgrokTunnel, and GitHub Actions Runner as Windows services.
#>

$ErrorActionPreference = "Stop"
$LogFile = "C:\Users\YDX2\dev\Youtube-Downloader\logs\setup-output.log"

# Ensure logs dir exists
New-Item -ItemType Directory -Path "C:\Users\YDX2\dev\Youtube-Downloader\logs" -Force | Out-Null

# Redirect all output to log
Start-Transcript -Path $LogFile -Force

try {
    $ProjectDir  = "C:\Users\YDX2\dev\Youtube-Downloader"
    $RunnerDir   = "C:\Users\YDX2\actions-runner"
    $PythonExe   = "C:\Users\YDX2\AppData\Local\Python\pythoncore-3.14-64\python.exe"
    $NgrokExe    = (Get-Command ngrok).Source
    $NssmExe     = "C:\Users\YDX2\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
    $NgrokDomain = "nonimpregnated-georgine-thetically.ngrok-free.dev"
    $ServerPort  = 8001

    Write-Host "Python: $PythonExe"
    Write-Host "Ngrok: $NgrokExe"
    Write-Host "NSSM: $NssmExe"

    # 1. YoutubeDownloader
    Write-Host "`n=== Installing YoutubeDownloader ===" -ForegroundColor Cyan
    $svc = "YoutubeDownloader"
    $ErrorActionPreference = "SilentlyContinue"
    $s = & $NssmExe status $svc 2>&1
    $ErrorActionPreference = "Stop"
    if ("$s" -match "SERVICE_") {
        Write-Host "Removing existing $svc..."
        & $NssmExe stop $svc 2>&1 | Out-Null
        & $NssmExe remove $svc confirm
    }
    & $NssmExe install $svc $PythonExe "$ProjectDir\server.py"
    & $NssmExe set $svc AppDirectory $ProjectDir
    & $NssmExe set $svc DisplayName "YouDescribe YouTube Downloader"
    & $NssmExe set $svc Start SERVICE_AUTO_START
    & $NssmExe set $svc AppStdout "$ProjectDir\logs\service-stdout.log"
    & $NssmExe set $svc AppStderr "$ProjectDir\logs\service-stderr.log"
    & $NssmExe set $svc AppRotateFiles 1
    & $NssmExe set $svc AppRotateBytes 10485760
    & $NssmExe start $svc
    Write-Host "$svc done." -ForegroundColor Green

    # 2. NgrokTunnel
    Write-Host "`n=== Installing NgrokTunnel ===" -ForegroundColor Cyan
    $svc = "NgrokTunnel"
    $ErrorActionPreference = "SilentlyContinue"
    $s = & $NssmExe status $svc 2>&1
    $ErrorActionPreference = "Stop"
    if ("$s" -match "SERVICE_") {
        Write-Host "Removing existing $svc..."
        & $NssmExe stop $svc 2>&1 | Out-Null
        & $NssmExe remove $svc confirm
    }
    & $NssmExe install $svc $NgrokExe "http --url=$NgrokDomain $ServerPort"
    & $NssmExe set $svc DisplayName "Ngrok Tunnel for YoutubeDownloader"
    & $NssmExe set $svc Start SERVICE_AUTO_START
    & $NssmExe set $svc AppStdout "$ProjectDir\logs\ngrok-stdout.log"
    & $NssmExe set $svc AppStderr "$ProjectDir\logs\ngrok-stderr.log"
    & $NssmExe set $svc AppRotateFiles 1
    & $NssmExe set $svc AppRotateBytes 10485760
    & $NssmExe start $svc
    Write-Host "$svc done." -ForegroundColor Green

    # 3. GitHubActionsRunner
    Write-Host "`n=== Installing GitHubActionsRunner ===" -ForegroundColor Cyan
    $svc = "GitHubActionsRunner"
    $ErrorActionPreference = "SilentlyContinue"
    $s = & $NssmExe status $svc 2>&1
    $ErrorActionPreference = "Stop"
    if ("$s" -match "SERVICE_") {
        Write-Host "Removing existing $svc..."
        & $NssmExe stop $svc 2>&1 | Out-Null
        & $NssmExe remove $svc confirm
    }
    & $NssmExe install $svc "$RunnerDir\run.cmd"
    & $NssmExe set $svc AppDirectory $RunnerDir
    & $NssmExe set $svc DisplayName "GitHub Actions Runner - Youtube-Downloader"
    & $NssmExe set $svc Start SERVICE_AUTO_START
    & $NssmExe set $svc AppStdout "$ProjectDir\logs\runner-stdout.log"
    & $NssmExe set $svc AppStderr "$ProjectDir\logs\runner-stderr.log"
    & $NssmExe set $svc AppRotateFiles 1
    & $NssmExe set $svc AppRotateBytes 10485760
    & $NssmExe start $svc
    Write-Host "$svc done." -ForegroundColor Green

    # Summary
    Write-Host "`n=== Status ===" -ForegroundColor Cyan
    Write-Host "YoutubeDownloader  : $(& $NssmExe status YoutubeDownloader)"
    Write-Host "NgrokTunnel        : $(& $NssmExe status NgrokTunnel)"
    Write-Host "GitHubActionsRunner: $(& $NssmExe status GitHubActionsRunner)"
    Write-Host "`nAll services installed. Server: http://localhost:$ServerPort | Public: https://$NgrokDomain" -ForegroundColor Green

} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor Red
}

Stop-Transcript

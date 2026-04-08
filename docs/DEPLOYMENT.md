# Deployment & Operations Guide

This document describes the end-to-end deployment pipeline for the Youtube-Downloader service, including how code gets from GitHub to the running server, how environment variables are managed, and how to troubleshoot common issues.

## Overview

The Youtube-Downloader runs on a **local Windows PC** (not a cloud server) because YouTube blocks downloads from data center IPs. The service must run on a residential IP. We use **ngrok** to expose the local server to the internet with a stable public URL.

```
Developer pushes to main
        │
        ▼
GitHub Actions triggers deploy workflow
        │
        ▼
Self-hosted runner (on the same PC) picks up the job
        │
        ├── Pulls latest code from GitHub
        ├── Generates .env from GitHub Variables
        ├── Installs Python dependencies
        └── Restarts the YoutubeDownloader Windows service
        │
        ▼
Server is live at http://localhost:8001
Exposed publicly via ngrok at https://nonimpregnated-georgine-thetically.ngrok-free.dev
```

## Components

### Three Windows Services

All three run as Windows services via [nssm](https://nssm.cc/) (Non-Sucking Service Manager). They auto-start on boot and restart on crash.

| Service Name | What It Does | Executable |
|---|---|---|
| `YoutubeDownloader` | FastAPI server (port 8001) — downloads YouTube videos, uploads to S3 | `python.exe server.py` |
| `NgrokTunnel` | Exposes port 8001 on the public ngrok domain | `ngrok http --url=<domain> --authtoken=<token> 8001` |
| `GitHubActionsRunner` | Self-hosted GitHub Actions runner for CI/CD | `actions-runner\run.cmd` |

### Key Paths on the PC

| Path | Purpose |
|---|---|
| `C:\Users\YDX2\dev\Youtube-Downloader` | Project source code |
| `C:\Users\YDX2\actions-runner` | GitHub Actions runner installation |
| `C:\Users\YDX2\dev\Youtube-Downloader\logs\` | Service logs (stdout/stderr for all 3 services) |
| `C:\Users\YDX2\Downloads\YouDescribeDownloadedVideos` | Temporary video download directory |

### Log Files

| Log File | Contents |
|---|---|
| `logs/service-stdout.log` | YoutubeDownloader server output |
| `logs/service-stderr.log` | YoutubeDownloader errors |
| `logs/ngrok-stdout.log` | Ngrok tunnel output |
| `logs/ngrok-stderr.log` | Ngrok tunnel errors |
| `logs/runner-stdout.log` | GitHub Actions runner output |
| `logs/runner-stderr.log` | GitHub Actions runner errors |
| `downloader.log` | Application-level download/upload logs |

Logs rotate at 10 MB (configured via nssm `AppRotateBytes`).

## CI/CD Pipeline

### How It Works

The pipeline is defined in `.github/workflows/deploy.yml`. It triggers on:
- **Push to `main`** — automatic deploy on every merge/push
- **`workflow_dispatch`** — manual trigger from GitHub Actions UI (useful for pushing env variable changes without a code commit)

### Deploy Steps

1. **Pull latest code**: `git fetch origin main && git reset --hard origin/main` in the project directory
2. **Generate `.env`**: Reads all values from GitHub Variables and writes them to `.env` (no BOM, UTF-8)
3. **Install dependencies**: `pip install -r requirements.txt`
4. **Restart server**: Stops and starts the `YoutubeDownloader` service via nssm, with a retry if the first start fails

### Important Implementation Details

- **All steps use PowerShell** (not bash), because the runner runs as `NT AUTHORITY\SYSTEM` which doesn't have Git Bash in its PATH
- **Absolute paths to all executables** (`git.exe`, `pip.exe`, `nssm.exe`) because SYSTEM's PATH differs from the user's
- **`git safe.directory`** is configured in the workflow because the repo is owned by user `YDX2` but the runner runs as `SYSTEM`
- **`.env` is written without UTF-8 BOM** using `[System.IO.File]::WriteAllText()` — PowerShell's `Set-Content -Encoding UTF8` adds a BOM that breaks `python-dotenv`

## Environment Variables

Environment variables are **not stored in the repo**. They are managed via **GitHub Repository Variables** and written to `.env` on every deploy.

### Viewing / Editing Variables

**Via GitHub UI:**
Go to repo Settings > Secrets and variables > Actions > Variables tab

**Via CLI (from the PC):**
```powershell
# List all variables
gh variable list

# Update a variable
gh variable set PORT --body "8002"

# After updating, trigger a deploy to apply
gh workflow run deploy.yml
```

### Current Variables

| Variable | Description |
|---|---|
| `AWS_ACCESS_KEY_ID` | AWS access key for S3 uploads |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key for S3 uploads |
| `AWS_REGION` | AWS region (currently `us-west-1`) |
| `S3_BUCKET_NAME` | S3 bucket name for video storage |
| `DOWNLOAD_DIR` | Absolute path to local download directory |
| `PORT` | Server port (currently `8001`) |

**Important:** `DOWNLOAD_DIR` must be an absolute path (e.g., `C:/Users/YDX2/Downloads/...`), not `~/...`. The service runs as SYSTEM, so `~` resolves to the SYSTEM profile, not the user's home.

### Updating a Variable Without Code Changes

1. Update the variable in GitHub (UI or CLI)
2. Go to Actions tab > "Deploy to Local PC" workflow > "Run workflow" button
3. The workflow re-generates `.env` and restarts the server

## First-Time Setup on a New Machine

If you ever need to set this up on a different PC:

### Prerequisites

- Python 3.12+ installed
- Git installed
- ngrok installed and authenticated (`ngrok config add-authtoken <token>`)
- nssm installed (`winget install nssm.nssm`)
- GitHub CLI installed and authenticated (`winget install GitHub.cli`, then `gh auth login`)

### Steps

1. **Clone the repo:**
   ```bash
   git clone https://github.com/serinaqin/Youtube-Downloader.git C:\Users\<user>\dev\Youtube-Downloader
   cd C:\Users\<user>\dev\Youtube-Downloader
   git checkout main
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up the GitHub Actions runner:**
   ```bash
   mkdir C:\Users\<user>\actions-runner && cd C:\Users\<user>\actions-runner
   # Download the latest runner from https://github.com/actions/runner/releases
   # Extract it, then:
   ./config.cmd --url https://github.com/serinaqin/Youtube-Downloader --token <REGISTRATION_TOKEN> --name <runner-name> --labels self-hosted,windows --unattended
   ```
   Get a registration token via: `gh api repos/serinaqin/Youtube-Downloader/actions/runners/registration-token --method POST`

4. **Update paths in scripts** if the username or Python install location differs:
   - `.github/workflows/deploy.yml` — update `PROJECT_DIR`, `NSSM_EXE`, `GIT_EXE`, `PIP_EXE`
   - `scripts/setup-all-services.ps1` — update `$ProjectDir`, `$RunnerDir`, `$PythonExe`, `$NssmExe`

5. **Set PowerShell execution policy** (run as Administrator):
   ```powershell
   Set-ExecutionPolicy RemoteSigned -Scope LocalMachine -Force
   ```

6. **Install Windows services** (run as Administrator):
   ```powershell
   .\scripts\setup-all-services.ps1
   ```
   This registers all 3 services with auto-start. Check `logs/setup-output.log` for results.

7. **Set git safe.directory** (run as Administrator):
   ```powershell
   & "C:\Program Files\Git\bin\git.exe" config --system --add safe.directory C:/Users/<user>/dev/Youtube-Downloader
   ```

8. **Verify everything:**
   ```bash
   # Check services
   Get-Service YoutubeDownloader,NgrokTunnel,GitHubActionsRunner

   # Check health
   curl http://localhost:8001/health

   # Check ngrok tunnel
   curl http://localhost:4040/api/tunnels

   # Check runner is online
   gh api repos/serinaqin/Youtube-Downloader/actions/runners --jq '.runners[]'
   ```

## Troubleshooting

### Service won't start (SERVICE_PAUSED)

`SERVICE_PAUSED` means the process started but exited immediately. nssm throttles restarts to prevent a loop.

```powershell
# Check the error log
Get-Content C:\Users\YDX2\dev\Youtube-Downloader\logs\service-stderr.log -Tail 20

# Try running manually to see the error
cd C:\Users\YDX2\dev\Youtube-Downloader
python server.py

# After fixing, restart:
nssm stop YoutubeDownloader
nssm start YoutubeDownloader
```

### Ngrok endpoint already in use (ERR_NGROK_334)

Another ngrok process is using the same domain. Kill it first:
```powershell
Get-Process ngrok | Stop-Process -Force
nssm restart NgrokTunnel
```

### Deploy workflow fails at "Pull latest code"

- **"bash: command not found"** — Workflow must use `shell: powershell`, not `shell: bash`
- **"dubious ownership"** — The `git safe.directory` config is missing for SYSTEM. The workflow sets this automatically, but if git itself is updated, it may need to be re-added
- **"authentication failed"** — The repo may have changed visibility or the runner's git credentials expired. Re-authenticate git on the PC

### Deploy workflow fails at "Restart server"

- Check `logs/service-stderr.log` for Python errors
- Most common cause: `.env` is malformed (check for BOM or leading whitespace)
- Verify manually: `python server.py` from the project directory

### Runner goes offline

```powershell
# Check service status
Get-Service GitHubActionsRunner

# Restart it
nssm restart GitHubActionsRunner

# If runner config is corrupted, re-register:
cd C:\Users\YDX2\actions-runner
./config.cmd remove --token <TOKEN>
./config.cmd --url https://github.com/serinaqin/Youtube-Downloader --token <TOKEN> --name youtube-downloader-pc --unattended
nssm restart GitHubActionsRunner
```

### Checking service status

```powershell
# Quick status of all services
Get-Service YoutubeDownloader,NgrokTunnel,GitHubActionsRunner | Format-Table Name,Status

# Detailed nssm info
$nssm = "C:\Users\YDX2\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
& $nssm status YoutubeDownloader
& $nssm status NgrokTunnel
& $nssm status GitHubActionsRunner
```

## Common Maintenance Tasks

### Changing the Ngrok Domain

If you need to use a different ngrok endpoint (e.g., new ngrok account, different domain):

1. **Reserve a new domain** at https://dashboard.ngrok.com/domains (requires a free or paid ngrok account)

2. **Get the authtoken** for the new account at https://dashboard.ngrok.com/get-started/your-authtoken

3. **Update the NgrokTunnel service** (run as Administrator):
   ```powershell
   $nssm = "C:\Users\YDX2\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"

   # Update the command arguments with the new domain and authtoken
   & $nssm stop NgrokTunnel
   & $nssm set NgrokTunnel AppParameters "http --url=<NEW_DOMAIN>.ngrok-free.dev --authtoken=<NEW_AUTHTOKEN> 8001"
   & $nssm start NgrokTunnel
   ```

4. **Verify the tunnel is active:**
   ```powershell
   curl http://localhost:4040/api/tunnels
   ```

5. **Update the YouDescribeX-API** (or any upstream caller) to use the new public URL

> **Note:** The ngrok authtoken is baked into the nssm service parameters, not the `.env` file. If you also update `scripts/setup-all-services.ps1`, update `$NgrokDomain` there for future re-installs.

### Updating the GitHub Actions Runner

GitHub periodically releases new runner versions. The runner auto-updates in most cases, but if you need to manually update or reinstall:

1. **Remove the old runner** (run as Administrator):
   ```powershell
   $nssm = "C:\Users\YDX2\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
   & $nssm stop GitHubActionsRunner

   cd C:\Users\YDX2\actions-runner
   # Get a removal token
   # gh api repos/serinaqin/Youtube-Downloader/actions/runners/registration-token --method POST
   ./config.cmd remove --token <REMOVAL_TOKEN>
   ```

2. **Download the new runner:**
   ```powershell
   cd C:\Users\YDX2\actions-runner
   # Download the latest from https://github.com/actions/runner/releases
   # Remove old files (keep _diag/ if you want logs), extract new zip
   ```

3. **Re-register:**
   ```powershell
   # Get a fresh registration token
   # gh api repos/serinaqin/Youtube-Downloader/actions/runners/registration-token --method POST
   ./config.cmd --url https://github.com/serinaqin/Youtube-Downloader --token <REG_TOKEN> --name youtube-downloader-pc --labels self-hosted,windows --unattended
   ```

4. **Restart the service:**
   ```powershell
   & $nssm start GitHubActionsRunner

   # Verify it's online
   gh api repos/serinaqin/Youtube-Downloader/actions/runners --jq '.runners[] | {name, status}'
   ```

### Updating nssm

If you need to update nssm (e.g., after a `winget upgrade`):

1. Find the new nssm path:
   ```powershell
   where.exe nssm
   # or check: C:\Users\YDX2\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM*
   ```

2. Update the path in:
   - `.github/workflows/deploy.yml` — the `NSSM_EXE` env var
   - `scripts/setup-all-services.ps1` — the `$NssmExe` variable

3. Commit and push the change. The running services are unaffected — nssm is only called during install/restart, not while the service is running.

### Updating Python

If you upgrade Python on the PC:

1. Find the new Python executable path:
   ```powershell
   where.exe python
   # Use the real path, NOT the WindowsApps shim
   ```

2. Reinstall dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. **Update the YoutubeDownloader service** (run as Administrator):
   ```powershell
   $nssm = "C:\Users\YDX2\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
   & $nssm stop YoutubeDownloader
   & $nssm set YoutubeDownloader Application "C:\Users\YDX2\AppData\Local\Python\<NEW_VERSION>\python.exe"
   & $nssm start YoutubeDownloader
   ```

4. Update the pip path in `.github/workflows/deploy.yml` (`PIP_EXE` env var)

5. Update the Python path in `scripts/setup-all-services.ps1` (`$PythonExe` variable)

> **Important:** The Windows Store Python shim (`C:\Users\YDX2\AppData\Local\Microsoft\WindowsApps\python.exe`) does NOT work as a Windows service. Always use the real Python executable path.

### Moving to a Different PC

See [First-Time Setup on a New Machine](#first-time-setup-on-a-new-machine) above. Additionally:

1. Remove the runner from the old PC first (`./config.cmd remove`)
2. Update all hardcoded paths in the workflow and scripts to match the new machine
3. The ngrok domain stays the same — just install ngrok on the new PC with the same authtoken
4. GitHub Variables don't need to change unless the `DOWNLOAD_DIR` path differs

## Architecture Decisions

| Decision | Why |
|---|---|
| **Self-hosted runner** (not webhooks or polling) | Native GitHub Actions integration, runs as a Windows service, handles pull+rebuild natively |
| **nssm** for services (not Task Scheduler) | Crash recovery with auto-restart, proper service management, log rotation |
| **GitHub Variables** (not Secrets) for `.env` | Variables are readable/editable in the UI, making it easier for maintainers. The PC is not shared, so visibility in logs is acceptable |
| **PowerShell** in workflow (not bash) | Runner runs as SYSTEM which doesn't have Git Bash in PATH |
| **`git reset --hard`** in deploy (not checkout) | The service runs from a fixed directory, not the runner's workspace. Hard reset ensures clean state matching the remote |
| **Absolute paths everywhere** | SYSTEM user has a different PATH than the logged-in user. Explicit paths prevent "command not found" errors |

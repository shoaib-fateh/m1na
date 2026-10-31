$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$entryPoint = Join-Path $projectRoot "mina.py"
$pythonw = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"

if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {
    $launcher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($launcher) {
        $pythonExe = (& $launcher.Source -3.12 -c "import sys; print(sys.executable)" 2>$null)
        if ($LASTEXITCODE -eq 0 -and $pythonExe) {
            $pythonw = Join-Path (Split-Path -Parent $pythonExe.Trim()) "pythonw.exe"
        }
    }

    if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {
        $pythonCommand = Get-Command "python.exe" -ErrorAction SilentlyContinue
        if ($pythonCommand) {
            $version = & $pythonCommand.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $version.Trim() -eq "3.12") {
                $pythonw = Join-Path (Split-Path -Parent $pythonCommand.Source) "pythonw.exe"
            }
        }
    }
}

if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {
    throw "pythonw.exe was not found at '$pythonw'. Install the GUI-enabled Python runtime."
}

$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction `
    -Execute $pythonw `
    -Argument "`"$entryPoint`"" `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal `
    -UserId $user `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName "Mina Desktop Companion" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Starts Mina in the current user's desktop session." `
    -Force | Out-Null

Write-Host "Installed the Mina logon task for $user. Mina will start at the next sign-in."

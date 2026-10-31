$ErrorActionPreference = "Stop"

$task = Get-ScheduledTask `
    -TaskName "Mina Desktop Companion" `
    -ErrorAction SilentlyContinue
if ($task) {
    Unregister-ScheduledTask `
        -TaskName "Mina Desktop Companion" `
        -Confirm:$false
    Write-Host "Removed the Mina logon task."
}
else {
    Write-Host "The Mina logon task is not installed."
}

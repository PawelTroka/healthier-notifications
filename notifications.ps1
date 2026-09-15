# Run from any working directory; all generated local data belongs to this repo.
$ErrorActionPreference = 'Stop'
$taskPython = Get-Command python -ErrorAction SilentlyContinue
if (-not $taskPython) {
    throw 'Python 3.10 or later is required. Install Python, then rerun this command.'
}
Push-Location -LiteralPath $PSScriptRoot
try {
    & $taskPython.Source -m healthier_notifications @args
    $taskExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $taskExitCode

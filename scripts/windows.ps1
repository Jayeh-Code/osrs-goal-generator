param(
    [ValidateSet('desktop','runelite','build','test','check','setup')]
    [string]$Action = 'check',
    [string]$PythonPath = $env:OSRS_PYTHON,
    [string]$JavaHome = $env:JAVA_HOME
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$venv = if ($env:OSRS_VENV) { $env:OSRS_VENV } else { Join-Path $env:LOCALAPPDATA 'OSRSGoalGenerator/desktop-venv' }
# Store-packaged Codex redirects LocalAppData writes. Reuse its installed environment
# when these launchers are later run from ordinary Explorer/PowerShell.
if (-not $env:OSRS_VENV -and -not (Test-Path (Join-Path $venv 'Scripts/python.exe'))) {
    $packages = Join-Path $env:LOCALAPPDATA 'Packages'
    $codexPackages = Get-ChildItem $packages -Directory -Filter 'OpenAI.Codex_*' -ErrorAction SilentlyContinue
    foreach ($package in $codexPackages) {
        $prepared = Join-Path $package.FullName 'LocalCache/Local/OSRSGoalGenerator/desktop-venv'
        if (Test-Path (Join-Path $prepared 'Scripts/python.exe')) { $venv = $prepared; break }
    }
}
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program exited with code $LASTEXITCODE" }
}
function Find-Python {
    $ErrorActionPreference = 'Continue'
    $candidates = @()
    if ($PythonPath) { $candidates += $PythonPath }
    $candidates += (Join-Path $venv 'Scripts/python.exe')
    foreach ($name in @('python','python3')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { $candidates += $command.Source }
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $located = & $py.Source -3 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0) { $candidates += $located }
    }
    # Optional fallback for this prepared Codex workspace; not a bundled app runtime.
    $candidates += (Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        & $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return $candidate }
    }
    throw 'Python 3.11+ was not found. Install Python or set OSRS_PYTHON to python.exe.'
}
function Find-Java {
    $candidates = @()
    if ($JavaHome) { $candidates += $JavaHome }
    $workspaceJdks = Join-Path $root '../../../work/jdk21'
    if (Test-Path $workspaceJdks) {
        $candidates += @(Get-ChildItem $workspaceJdks -Directory | ForEach-Object { $_.FullName })
    }
    $command = Get-Command java -ErrorAction SilentlyContinue
    if ($command) { $candidates += (Split-Path (Split-Path $command.Source -Parent) -Parent) }
    foreach ($candidate in $candidates) {
        if (-not (Test-Path (Join-Path $candidate 'bin/javac.exe'))) { continue }
        $release = Join-Path $candidate 'release'
        if (-not (Test-Path $release)) { continue }
        $versionLine = Get-Content $release | Where-Object { $_ -match '^JAVA_VERSION=' } | Select-Object -First 1
        if ($versionLine -match 'JAVA_VERSION="(\d+)') {
            $major = [int]$Matches[1]
            if ($major -ge 11 -and $major -le 23) { return $candidate }
        }
    }
    throw 'No JDK compatible with Gradle 8.10 was found. Install JDK 21 and set JAVA_HOME to its directory.'
}
try {
    if ($Action -in @('runelite','build','check')) {
        $jdk = Find-Java
        $env:JAVA_HOME = $jdk
        Write-Host "Java: $jdk"
        if ($Action -ne 'check') {
            Push-Location (Join-Path $root 'runelite_companion')
            try {
                $task = if ($Action -eq 'runelite') { 'run' } else { 'build' }
                Invoke-Checked (Join-Path $PWD 'gradlew.bat') @('--project-cache-dir','.gradle-user','--no-daemon',$task)
            } finally { Pop-Location }
        }
    }
    if ($Action -in @('desktop','test','check','setup')) {
        $python = Find-Python
        Write-Host "Python: $python"
        Push-Location (Join-Path $root 'desktop_app')
        try {
            if ($Action -eq 'setup') {
                if (-not (Test-Path (Join-Path $venv 'Scripts/python.exe'))) { Invoke-Checked $python @('-m','venv',$venv) }
                Invoke-Checked (Join-Path $venv 'Scripts/python.exe') @('-m','pip','install','-r','requirements.txt')
            } elseif ($Action -eq 'test') {
                $env:PYTHONPATH = Join-Path $PWD 'src'
                Invoke-Checked $python @('-m','unittest','discover','-s','tests','-v')
                Invoke-Checked $python @('-m','compileall','-q','src','tests','run.py')
            } else {
                & $python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PySide6') else 1)"
                if ($LASTEXITCODE -ne 0) { throw 'PySide6 is missing. Run Setup Desktop.cmd once, then retry.' }
                if ($Action -eq 'desktop') { Invoke-Checked $python @('run.py') }
                else { Write-Host 'Desktop dependencies ready. No application was launched.' }
            }
        } finally { Pop-Location }
    }
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

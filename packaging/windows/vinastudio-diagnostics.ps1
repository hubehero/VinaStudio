<#
.SYNOPSIS
    Collect everything a Windows-side rendering or dependency report needs.

.DESCRIPTION
    A defect report that cannot be reproduced away from the reporter's machine has
    to travel to the maintainer as data. This gathers it in one pass: the graphics
    adapters and their driver versions (the single fact nothing else can supply),
    the OS build, the installed application, its own log, and the live API's
    answers about its docking backend and its renderer.

    Read-only. It starts nothing, changes nothing, needs no administrator rights,
    and writes only into its output folder.

.PARAMETER OutDir
    Where the report is written. Defaults to a timestamped folder on the Desktop.

.PARAMETER NoScreenshot
    Skip the screen capture. The capture is the record of what the app looked
    like, including the "实际渲染器" row on the 环境自检 page.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\vinastudio-diagnostics.ps1
#>
[CmdletBinding()]
param(
    [string] $OutDir = (Join-Path ([Environment]::GetFolderPath('Desktop')) ("vinastudio-diagnostics-{0}" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))),
    [switch] $NoScreenshot
)

$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$report = New-Object System.Collections.Generic.List[string]

function Say([string] $Text) {
    Write-Host $Text
    $report.Add($Text)
}

function Section([string] $Name) {
    Say ''
    Say ('=== {0} {1}' -f $Name, ('=' * [Math]::Max(1, 62 - $Name.Length)))
}

function Try-Collect([string] $Name, [scriptblock] $Work) {
    # A diagnostic that dies on its third probe is worth less than one that
    # reports what it could not read and keeps going.
    try {
        Section $Name
        & $Work
    } catch {
        Say ("<unavailable: {0}>" -f $_.Exception.Message)
    }
}

Try-Collect 'Report' {
    Say ("generated   : {0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), (Get-TimeZone).Id)
    Say ("powerShell  : {0}" -f $PSVersionTable.PSVersion)
    Say ("is 64-bit   : {0}" -f [Environment]::Is64BitProcess)
    Say ("elevated    : {0}" -f ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))
}

Try-Collect 'Operating system' {
    $os = Get-CimInstance Win32_OperatingSystem
    $build = [int]($os.BuildNumber)
    Say ("caption     : {0}" -f $os.Caption)
    Say ("version     : {0} (build {1}{2})" -f $os.Version, $os.BuildNumber, $(if ($build -ge 22000) { ', Windows 11' } else { ', Windows 10' }))
    Say ("architecture: {0} / {1}" -f $os.OSArchitecture, $os.SystemType)
    Say ("install     : {0}" -f $os.InstallDate)
    Say ("ram total   : {0:N1} GB" -f ($os.TotalVisibleMemorySize / 1MB))
    Say ("ram free    : {0:N1} GB" -f ($os.FreePhysicalMemory / 1MB))
    Get-CimInstance Win32_Processor |
        ForEach-Object { Say ("cpu         : {0} ({1}C/{2}T)" -f $_.Name.Trim(), $_.NumberOfCores, $_.NumberOfLogicalProcessors) }
}

# The adapters and their driver versions are the reason this script exists: a
# rendering defect that only appears on one machine is usually that machine's
# driver, and no other artefact can say which driver it was.
Try-Collect 'Graphics adapters' {
    $adapters = @(Get-CimInstance Win32_VideoController)
    if ($adapters.Count -eq 0) { Say '<no adapters reported>' }
    foreach ($a in $adapters) {
        Say ("adapter     : {0}" -f $a.Name)
        Say ("  vendor    : {0}" -f $a.AdapterCompatibility)
        Say ("  driver    : {0} dated {1}" -f $a.DriverVersion, $a.DriverDate)
        Say ("  processor : {0}" -f $a.VideoProcessor)
        Say ("  memory    : {0:N0} MB" -f ($a.AdapterRAM / 1MB))
        Say ("  status    : {0} {1}" -f $a.Status, $a.StatusDescription)
        Say ("  device id : {0}" -f $a.PNPDeviceID)
        Say ("  mode      : {0}x{1} @ {2} Hz" -f $a.CurrentHorizontalResolution, $a.CurrentVerticalResolution, $a.CurrentRefreshRate)
    }
    Get-CimInstance Win32_DesktopMonitor |
        ForEach-Object { Say ("monitor     : {0}x{1} [{2}]" -f $_.ScreenWidth, $_.ScreenHeight, $_.Name) }
}

Try-Collect 'Installed application' {
    # Built with a loop rather than one expression: a null root would make
    # Join-Path throw and cost the whole section, not just one candidate path.
    $candidates = @()
    foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
        if (-not $root) { continue }
        $candidates += (Join-Path $root 'VinaStudio\vinastudio.exe')
        $candidates += (Join-Path $root 'Programs\VinaStudio\vinastudio.exe')
    }
    $candidates = $candidates | Select-Object -Unique
    $found = $false
    foreach ($exe in $candidates) {
        if (Test-Path $exe) {
            $found = $true
            $vi = (Get-Item $exe).VersionInfo
            Say ("path        : {0}" -f $exe)
            Say ("  version   : {0} (file {1})" -f $vi.ProductVersion, $vi.FileVersion)
            Say ("  written   : {0}" -f (Get-Item $exe).LastWriteTime)
            Say ("  sha256    : {0}" -f (Get-FileHash $exe -Algorithm SHA256).Hash)
        }
    }
    if (-not $found) { Say '<not found in the usual install locations; paste the shortcut path if it is elsewhere>' }

    $procs = @(Get-Process -Name 'vinastudio*' -ErrorAction SilentlyContinue)
    if ($procs.Count -eq 0) {
        Say '<the application is NOT running; the API snapshot below will be empty>'
    }
    foreach ($p in $procs) {
        Say ("running     : pid {0} {1}" -f $p.Id, $p.Path)
        Say ("  window    : '{0}'" -f $p.MainWindowTitle)
        Say ("  started   : {0}" -f $p.StartTime)
        Say ("  workingSet: {0:N0} MB" -f ($p.WorkingSet64 / 1MB))
    }
    # Chromium's helper processes are where a rendering decision ends up.
    $helpers = @(Get-Process -Name 'QtWebEngineProcess' -ErrorAction SilentlyContinue)
    Say ("webengine   : {0} helper process(es)" -f $helpers.Count)
    foreach ($h in $helpers) { Say ("  pid {0}: {1:N0} MB" -f $h.Id, ($h.WorkingSet64 / 1MB)) }
}

Try-Collect 'Application data directory' {
    $home_ = if ($env:VINASTUDIO_HOME) { $env:VINASTUDIO_HOME } else { Join-Path $env:USERPROFILE '.vinastudio' }
    Say ("app home    : {0}" -f $home_)
    if (-not (Test-Path $home_)) { Say '<absent: the application has never run for this user>'; return }
    $wsFile = Join-Path $home_ 'workspace.json'
    if (Test-Path $wsFile) {
        Say ('workspace   : {0}' -f (Get-Content $wsFile -Raw).Trim())
    }
    $logs = Join-Path $home_ 'logs'
    if (Test-Path $logs) {
        Get-ChildItem $logs | ForEach-Object { Say ("log         : {0} ({1:N0} bytes, {2})" -f $_.Name, $_.Length, $_.LastWriteTime) }
    }
}

Try-Collect 'Application log' {
    $home_ = if ($env:VINASTUDIO_HOME) { $env:VINASTUDIO_HOME } else { Join-Path $env:USERPROFILE '.vinastudio' }
    $log = Join-Path $home_ 'logs\vinastudio.log'
    if (-not (Test-Path $log)) { Say '<no log found>'; return }
    $copy = Join-Path $OutDir 'vinastudio.log'
    Copy-Item $log $copy -Force
    Say ("copied      : {0}" -f $copy)
    $tail = Get-Content $log -Tail 60
    Say '--- last 60 lines'
    foreach ($line in $tail) { Say $line }

    # The API binds port 0, so the port only exists in this line; it is also what
    # lets the snapshot below reach a running instance without guessing.
    $matches_ = [regex]::Matches((Get-Content $log -Tail 4000 -Raw), 'listening on http://[^\s:/]+:(\d+)')
    if ($matches_.Count -gt 0) { Say ("port from log: {0}" -f $matches_[$matches_.Count - 1].Groups[1].Value) }
}

Try-Collect 'Live API snapshot' {
    $home_ = if ($env:VINASTUDIO_HOME) { $env:VINASTUDIO_HOME } else { Join-Path $env:USERPROFILE '.vinastudio' }
    $log = Join-Path $home_ 'logs\vinastudio.log'
    $ports = New-Object System.Collections.Generic.List[int]
    if (Test-Path $log) {
        $m = [regex]::Matches((Get-Content $log -Tail 4000 -Raw), 'listening on http://[^\s:/]+:(\d+)')
        foreach ($hit in $m) { $ports.Add([int]$hit.Groups[1].Value) }
    }
    # Fallback for a fresh instance whose log line has not been flushed yet.
    foreach ($p in @(Get-Process -Name 'vinastudio*' -ErrorAction SilentlyContinue)) {
        foreach ($c in @(Get-NetTCPConnection -State Listen -OwningProcess $p.Id -ErrorAction SilentlyContinue)) {
            $ports.Add([int]$c.LocalPort)
        }
    }
    $ports = $ports | Select-Object -Unique
    if (-not $ports) { Say '<no listening port found; start the application and run this script again>'; return }

    # The server refuses a foreign Origin, but a request without one is a script
    # request and is served — which is exactly what this is.
    $served = $false
    foreach ($port in ($ports | Sort-Object -Descending)) {
        foreach ($route in @('info', 'selfcheck')) {
            $url = "http://127.0.0.1:$port/api/system/$route"
            try {
                $body = Invoke-RestMethod -Uri $url -TimeoutSec 60
                $body | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $OutDir ("system-$route.json")) -Encoding UTF8
                $served = $true
                Say ("{0} -> system-{1}.json" -f $url, $route)
                if ($route -eq 'info') {
                    Say ("  platform  : {0} {1} {2}" -f $body.runtime.platform, $body.runtime.platformRelease, $body.runtime.machine)
                    Say ("  python    : {0}" -f $body.runtime.python)
                    Say ("  app home  : {0}" -f $body.home)
                    Say ("  softwareRenderRequested : {0}" -f $body.rendering.softwareRenderRequested)
                    Say ("  docking   : backend={0} reason={1} cli={2} module={3}" -f `
                        $body.docking.backend, $body.docking.reasonCode, $body.docking.cliAvailable, $body.docking.apiAvailable)
                    foreach ($name in $body.packages.PSObject.Properties.Name) {
                        Say ("  package   : {0} = {1}" -f $name, $body.packages.$name)
                    }
                }
                if ($route -eq 'selfcheck') {
                    Say ("  ok={0} dockingAvailable={1} dockingMissing=[{2}]" -f `
                        $body.ok, $body.dockingAvailable, ($body.dockingMissing -join ','))
                    Say ("  failed=[{0}]" -f ($body.failed -join ','))
                    foreach ($c in $body.checks) {
                        Say ("  check     : {0} importable={1} ms={2} {3}" -f $c.distribution, $c.importable, $c.importMs, $c.error)
                    }
                }
            } catch {
                Say ("{0} -> {1}" -f $url, $_.Exception.Message)
            }
        }
    }
    if (-not $served) { Say '<the API did not answer on any candidate port>' }
}

Try-Collect 'Relevant environment variables' {
    Get-ChildItem Env: |
        Where-Object { $_.Name -like 'VINASTUDIO_*' -or $_.Name -like 'QT_*' -or $_.Name -like 'QTWEBENGINE_*' } |
        Sort-Object Name |
        ForEach-Object { Say ("{0}={1}" -f $_.Name, $_.Value) }
}

if (-not $NoScreenshot) {
    Try-Collect 'Screenshot' {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
        $gfx = [System.Drawing.Graphics]::FromImage($bmp)
        $gfx.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        $shot = Join-Path $OutDir 'screen.png'
        $bmp.Save($shot, [System.Drawing.Imaging.ImageFormat]::Png)
        $gfx.Dispose()
        $bmp.Dispose()
        Say ("saved       : {0} ({1:N0} bytes)" -f $shot, (Get-Item $shot).Length)
    }
}

Section 'What still needs a human'
$todo = @(
    '1. Open 环境自检 (/environment) in the app and read the 运行环境 card.',
    '   Record 渲染模式 and 实际渲染器 verbatim -- that string is the renderer',
    '   Chromium actually chose, which decides whether the GPU is in use at all.',
    '2. On the 3D viewport, rotate the molecule by dragging for ~10 seconds.',
    '   Note: does it stutter (estimated fps), does the canvas flash or go blank,',
    '   and does it behave differently right after loading vs after a while?',
    '3. Screenshot (Win+Shift+S) while it misbehaves, and save it into this folder.',
    '4. If the GPU is disabled in 渲染模式: update the graphics driver (both the',
    '   Intel and the NVIDIA one), then repeat step 1 and say whether it changed.',
    '',
    '如需中文说明：把整个文件夹打包发回来即可，第 1、2 步的现象描述最有价值。'
)
foreach ($line in $todo) { Say $line }

$summary = Join-Path $OutDir 'summary.txt'
# North of PowerShell 5.1 this writes UTF-8 without a BOM, which is fine; under
# 5.1 it writes one, which is what keeps the Chinese lines from being decoded on
# the console's ANSI code page and coming back as mojibake.
Set-Content -Path $summary -Value $report -Encoding UTF8
Write-Host ''
Write-Host ("report written to: {0}" -f $OutDir)

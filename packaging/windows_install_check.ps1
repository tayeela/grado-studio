# ГРАДО 2 · ставит готовый установщик на чистый Windows, как владелец, запускает установленную программу и удаляет её.
# Вызывает .github/workflows/grado2-release.yml (job build, windows-latest) после Inno Setup; по шагам — packaging/README.md.
# Проверки программы и замеры — packaging/installed_check.py; итог пишется в сводку запуска ($env:GITHUB_STEP_SUMMARY).
param([Parameter(Mandatory = $true)][string]$Installer, [string]$Version = "", [int]$Port = 8875)
$ErrorActionPreference = "Stop"
$summary = if ($env:GITHUB_STEP_SUMMARY) { $env:GITHUB_STEP_SUMMARY } else { Join-Path $env:TEMP "grado2-install-summary.md" }
$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{6B2E4C1F-7A90-4D2B-9E34-2C5A7F0B8D11}_is1"
$data = Join-Path $env:LOCALAPPDATA "GRADO2"
function Say($line) { Write-Host $line; Add-Content -Path $summary -Value $line -Encoding utf8 }

Say "## Установка на чистом Windows ($([Environment]::OSVersion.VersionString))"
Say ""
Say "Установщик: ``$(Split-Path $Installer -Leaf)``, $([math]::Round((Get-Item $Installer).Length / 1MB, 1)) МБ"
if (Test-Path $data) { Remove-Item -Recurse -Force $data }          # пустой кэш и настройки, как на новом компьютере

# 1. установка без вопросов, только для текущего пользователя (без прав администратора), со значком на рабочем столе
$log = Join-Path $env:RUNNER_TEMP "grado2-setup.log"
$t = [Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath $Installer -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/TASKS=desktopicon", "/LOG=`"$log`"" -Wait -PassThru
$t.Stop()
if ($p.ExitCode -ne 0) { Get-Content $log -Tail 40; throw "installer exit code $($p.ExitCode)" }
$reg = Get-ItemProperty $key
$dir = $reg.InstallLocation.TrimEnd("\")
$exe = Join-Path $dir "ГРАДО 2.exe"
if (-not (Test-Path $exe)) { throw "no exe after install: $exe" }
if ($Version -and $reg.DisplayVersion -ne $Version) { throw "installed version $($reg.DisplayVersion) != $Version" }
$menu = Get-ChildItem -Recurse -Filter "ГРАДО 2.lnk" (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs") -ErrorAction SilentlyContinue
$desk = Test-Path (Join-Path ([Environment]::GetFolderPath("Desktop")) "ГРАДО 2.lnk")
if (-not $menu) { throw "no Start menu shortcut" }
if (-not $desk) { throw "no desktop shortcut" }
$size = [math]::Round(((Get-ChildItem -Recurse $dir | Measure-Object Length -Sum).Sum) / 1MB)
Say "Установилась за $([math]::Round($t.Elapsed.TotalSeconds, 1)) с в ``$dir`` ($size МБ), версия $($reg.DisplayVersion); значки в меню «Пуск» и на рабочем столе есть."
Say ""

# 2. первый запуск установленной программы (пустой кэш), проверки как у градостроителя, затем второй запуск
$env:GRADO2_NO_BROWSER = "1"; $env:GRADO2_NO_DIALOG = "1"; $env:GRADO2_PORT = "$Port"
$env:GRADO2_PROJECTS = Join-Path $env:RUNNER_TEMP "grado2-projects"
$url = "http://127.0.0.1:$Port"
foreach ($run in "Первый запуск (пустой кэш)", "Второй запуск") {
  Say "### $run"
  Say ""
  $app = Start-Process -FilePath $exe -PassThru
  try {
    $extra = if ($run -like "Первый*") { @("--portals") } else { @() }
    python packaging/installed_check.py --url $url --wait 90 --expect-version $Version --report $summary @extra
    if ($LASTEXITCODE -ne 0) {
      if (Test-Path (Join-Path $data "startup-error.log")) { Get-Content (Join-Path $data "startup-error.log") }
      throw "installed_check failed ($run)"
    }
  } finally { Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2 }
}
if (Test-Path (Join-Path $data "startup-error.log")) { Get-Content (Join-Path $data "startup-error.log"); throw "startup-error.log written" }

# 3. удаление: папка программы, значки и запись в «Установке и удалении программ» исчезают
$un = $reg.UninstallString.Trim('"')
$t = [Diagnostics.Stopwatch]::StartNew()
Start-Process -FilePath $un -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait
foreach ($i in 1..60) { if (-not (Test-Path $exe) -and -not (Test-Path $key)) { break }; Start-Sleep -Seconds 1 }   # деинсталлятор Inno перезапускает себя из TEMP
$t.Stop()
if (Test-Path $exe) { throw "exe still there after uninstall" }
if (Test-Path $key) { throw "uninstall record still there" }
if (Test-Path (Join-Path ([Environment]::GetFolderPath("Desktop")) "ГРАДО 2.lnk")) { throw "desktop shortcut still there" }
if (-not (Test-Path $data)) { throw "user data folder removed by uninstall: $data" }
Say "Удалилась за $([math]::Round($t.Elapsed.TotalSeconds, 1)) с: папки программы, значков и записи в списке программ нет; папка данных ``$data`` (кэш, настройки) осталась."

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$gccPath = 'C:\Program Files (x86)\Dev-Cpp\MinGW64\bin\gcc.exe'
if (-not (Test-Path -LiteralPath $gccPath)) {
    throw "GCC not found: $gccPath"
}

$testOutput = Join-Path $env:TEMP 'f28p65x_k230_smart_car_tests'
New-Item -ItemType Directory -Force -Path $testOutput | Out-Null

$control = Join-Path $projectRoot 'src\control'
$controlExe = Join-Path $testOutput 'control_tests.exe'
& $gccPath -std=c99 -Wall -Wextra -Werror -pedantic `
    -DCONTROL_HOST_TEST -I $control `
    (Join-Path $control 'pid.c') `
    (Join-Path $control 'encoder_snapshot.c') `
    (Join-Path $control 'motor_control.c') `
    (Join-Path $control 'line_sensor_filter.c') `
    (Join-Path $control 'line_follow.c') `
    (Join-Path $projectRoot 'tests\control_tests.c') `
    -o $controlExe
if ($LASTEXITCODE -ne 0) { throw 'Control test compile failed.' }
& $controlExe
if ($LASTEXITCODE -ne 0) { throw 'Control tests failed.' }

$linkExe = Join-Path $testOutput 'k230_link_tests.exe'
& $gccPath -std=c99 -Wall -Wextra -Werror -pedantic `
    -DK230_LINK_HOST_TEST `
    (Join-Path $projectRoot 'src\communication\k230_link.c') `
    (Join-Path $projectRoot 'src\communication\test\k230_link_parser_test.c') `
    -o $linkExe
if ($LASTEXITCODE -ne 0) { throw 'K230 parser test compile failed.' }
& $linkExe
if ($LASTEXITCODE -ne 0) { throw 'K230 parser tests failed.' }

Write-Host 'F28P65x smart-car host tests: PASS'


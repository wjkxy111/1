@echo off
setlocal
set "APP=%~dp0host_app\dist\RA8D1_EDGE_AI_STUDIO\RA8D1_EDGE_AI_STUDIO.exe"
if exist "%APP%" (
    start "RA8D1 Edge AI Studio" "%APP%" %*
) else (
    call "%~dp0host_app\run_host.bat" %*
)

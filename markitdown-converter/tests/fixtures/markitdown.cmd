@echo off
if "%~1"=="--version" (
  echo markitdown 0.1.6-test
  exit /b 0
)
if defined FAKE_MARKITDOWN_FAIL (
  echo simulated conversion failure 1>&2
  exit /b 9
)
set "target="
:parse
if "%~1"=="" goto convert
if "%~1"=="-o" (
  set "target=%~2"
  shift
)
shift
goto parse
:convert
if "%target%"=="" exit /b 8
>"%target%" echo # converted
>>"%target%" echo safe output
exit /b 0

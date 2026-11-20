@echo off
echo === Building Kurmanji-TTS for Windows ===
cd /d "%~dp0.."

rem Prefer the standard CPython build env: it can load sherpa-onnx wheels.
set "PY=.venv\bin\python.exe"
set "FLET=.venv\bin\flet.exe"
if exist ".build-venv\Scripts\python.exe" (
  set "PY=.build-venv\Scripts\python.exe"
  set "FLET=.build-venv\Scripts\flet.exe"
)

if not exist "%PY%" (
  echo [ERROR] Virtual environment not found. Run: python -m venv .venv then install requirements.txt
  exit /b 1
)

"%PY%" -m pip install pyinstaller
if errorlevel 1 exit /b 1
rem MSYS2 Python has no CA bundle configured; point urllib at certifi's bundle.
"%PY%" -c "import certifi;open('.certifi_path.tmp','w').write(certifi.where())"
set /p SSL_CERT_FILE=<.certifi_path.tmp
del /q .certifi_path.tmp
set "REQUESTS_CA_BUNDLE=%SSL_CERT_FILE%"

set "SHERPA_BINARIES="
if exist ".build-venv\Lib\site-packages\sherpa_onnx\lib" (
  set "SHERPA_BINARIES=--add-binary .build-venv\Lib\site-packages\sherpa_onnx\lib\*;sherpa_onnx\lib --hidden-import sherpa_onnx"
)

"%FLET%" pack main.py --name "Kurmanji-TTS" --add-data "THIRD-PARTY-LICENSES.md:." %SHERPA_BINARIES% -y
if errorlevel 1 exit /b 1
echo Copying runtime assets next to the executable...
xcopy /E /I /Y "models" "dist\models" >nul
xcopy /E /I /Y "piper" "dist\piper" >nul
copy /Y "THIRD-PARTY-LICENSES.md" "dist\" >nul
echo.
echo Build finished: dist\Kurmanji-TTS.exe
dir "dist\Kurmanji-TTS.exe"
if "%KURMANJI_NO_PAUSE%"=="" pause

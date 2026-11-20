$ErrorActionPreference = "Stop"
$root = "C:\Users\Luqman\Desktop\Projecton\kurmanji-tts\docs"
function Log($m) { Write-Output ("{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }
Remove-Item -Path "HKCU:\Software\Microsoft\Office\16.0\Word\Resiliency\DocumentRecovery" -Recurse -Force -ErrorAction SilentlyContinue
Log "resiliency-cleared"
$exe = (Get-ChildItem "C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE" -ErrorAction SilentlyContinue).FullName
if (-not $exe) { $exe = (Get-ChildItem "C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE" -ErrorAction SilentlyContinue).FullName }
Log ("exe=" + $exe)
Start-Process -FilePath $exe -ArgumentList "/a"
Start-Sleep -Seconds 10
Log "word-started"
$word = [Runtime.InteropServices.Marshal]::GetActiveObject("Word.Application")
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $word.Documents.Open((Join-Path $root "Kurmanji-TTS_Thesis_Rojava.docx"), $false)
Log "opened"
$doc.ExportAsFixedFormat((Join-Path $root "_safemode.pdf"), 17)
Log ("exported " + (Get-Item (Join-Path $root "_safemode.pdf")).Length)
$doc.Close($false)
$word.Quit()
Log "done"

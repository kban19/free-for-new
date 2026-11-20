$ErrorActionPreference = "Stop"
$root = "C:\Users\Luqman\Desktop\Projecton\kurmanji-tts\docs"
$out = Join-Path $root "_print.pdf"
function Log($m) { Write-Output ("{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }
if (Test-Path $out) { Remove-Item $out -Force }
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $word.ActivePrinter = "Microsoft Print to PDF"
  $doc = $word.Documents.Open((Join-Path $root "Kurmanji-TTS_Thesis_Rojava.docx"), $false)
  Log "opened"
  $doc.PrintOut($false, $false, 0, $out, 0, 0, 0, 1, "", 0, $true)
  Log "printout-returned"
  $doc.Close($false)
} finally { $word.Quit(); Log "quit" }

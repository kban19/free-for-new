$ErrorActionPreference = "Stop"
$root = "C:\Users\Luqman\Desktop\Projecton\kurmanji-tts\docs"
function Log($m) { Write-Output ("{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $doc = $word.Documents.Open((Join-Path $root "_q012.docx"), $false)
  Log "opened q012"
  $out = Join-Path $root "_q012.pdf"
  $doc.ExportAsFixedFormat($out, 17)
  Log ("exported " + (Get-Item $out).Length)
  $doc.Close($false)
} finally { $word.Quit(); Log "quit" }

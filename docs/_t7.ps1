$ErrorActionPreference = "Stop"
$root = "C:\Users\Luqman\Desktop\Projecton\kurmanji-tts\docs"
function Log($m) { Write-Output ("{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $doc = $word.Documents.Open((Join-Path $root "_old.docx"), $false)
  Log "opened old"
  $out = Join-Path $root "_old.pdf"
  $doc.ExportAsFixedFormat($out, 17)
  Log ("exported old " + (Get-Item $out).Length)
  $doc.Close($false)
} finally { $word.Quit(); Log "quit" }

$ErrorActionPreference = "Stop"
$root = "C:\Users\Luqman\Desktop\Projecton\kurmanji-tts\docs"
function Log($m) { Write-Output ("{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  foreach ($name in @("_q50")) {
    $doc = $word.Documents.Open((Join-Path $root ($name + ".docx")), $false)
    Log ("opened " + $name)
    $out = Join-Path $root ($name + ".pdf")
    $doc.ExportAsFixedFormat($out, 17)
    Log ("exported " + $name + " " + (Get-Item $out).Length)
    $doc.Close($false)
  }
} finally { $word.Quit(); Log "quit" }

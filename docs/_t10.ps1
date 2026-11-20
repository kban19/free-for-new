$ErrorActionPreference = "Stop"
$root = "C:\Users\Luqman\Desktop\Projecton\kurmanji-tts\docs"
function Log($m) { Write-Output ("{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $d1 = $word.Documents.Add()
  $d1.Content.Text = "plain test"
  Log "add-ready"
  $d1.ExportAsFixedFormat((Join-Path $root "_add.pdf"), 17)
  Log "add-exported"
  $d1.Close($false)
  $d2 = $word.Documents.Open((Join-Path $root "_plain.docx"), $false)
  Log "plain-opened"
  $d2.ExportAsFixedFormat((Join-Path $root "_plain.pdf"), 17)
  Log "plain-exported"
  $d2.Close($false)
} finally { $word.Quit(); Log "quit" }

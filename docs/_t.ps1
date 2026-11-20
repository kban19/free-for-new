$ErrorActionPreference = "Stop"
$out = "C:\Users\Luqman\Desktop\Projecton\kurmanji-tts\docs\_t.pdf"
function Log($m) { Write-Output ("{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $doc = $word.Documents.Add()
  $doc.Content.Text = "test"
  Log "doc-ready"
  $doc.ExportAsFixedFormat($out, 17)
  Log ("exported " + (Get-Item $out).Length)
  $doc.Close($false)
} finally { $word.Quit(); Log "quit" }

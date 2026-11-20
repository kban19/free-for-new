$ErrorActionPreference = "Stop"
$root = "C:\Users\Luqman\Desktop\Projecton\kurmanji-tts\docs"
$docx = Join-Path $root "Kurmanji-TTS_Thesis_Rojava.docx"
function Log($m) { Write-Output ("{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $doc = $word.Documents.Open($docx, $false)
  Log "opened"
  foreach ($r in @(1,21,41)) {
    $out = Join-Path $root ("_p{0}.pdf" -f $r)
    $doc.ExportAsFixedFormat($out, 17, $false, 0, $r, $r+19)
    Log ("exported {0} size={1}" -f $r, (Get-Item $out).Length)
  }
  $doc.Close($false)
  Log "closed"
} finally { $word.Quit(); Log "quit" }

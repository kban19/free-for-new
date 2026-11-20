$ErrorActionPreference = "Stop"
$root = "C:\Users\Luqman\Desktop\Projecton\kurmanji-tts\docs"
$docx = Join-Path $root "Kurmanji-TTS_Thesis_Rojava.docx"
$pdf  = Join-Path $root "_thesis_tmp.pdf"
function Log($m) { Write-Output ("{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $doc = $word.Documents.Open($docx, $false)
  Log "opened"
  $doc.SaveAs2($pdf, 17)
  Log ("saved " + (Get-Item $pdf).Length)
  $doc.Close($false)
  Log "closed"
} finally { $word.Quit(); Log "quit" }

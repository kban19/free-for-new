$ErrorActionPreference = "Stop"
$root = "C:\Users\Luqman\Desktop\Projecton\kurmanji-tts"
$docx = Join-Path $root "docs\Kurmanji-TTS_Thesis_Rojava.docx"
$pdf  = Join-Path $root "docs\_thesis_tmp.pdf"
function Log($m) { Write-Output ("{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$word.AutomationSecurity = 3
$word.Options.UpdateFieldsAtPrint = $false
try {
  $doc = $word.Documents.Open($docx, $false, $false, $false)
  Log "opened"
  $doc.Fields.Update() | Out-Null
  foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
  $doc.Repaginate()
  Log ("stats pages={0} words={1}" -f $doc.ComputeStatistics(2), $doc.ComputeStatistics(0))
  Log ("before-export exists=" + (Test-Path $pdf))
  $doc.ExportAsFixedFormat($pdf, 17)
  Log ("exported size=" + (Get-Item $pdf).Length)
  $doc.Close($false)
  Log "closed"
} finally {
  $word.Quit()
  Log "quit"
}

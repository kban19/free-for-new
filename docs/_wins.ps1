Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
"@
$targets = (Get-Process WINWORD -ErrorAction SilentlyContinue).Id
$found = @()
$cb = [W+EnumProc]{
  param($h,$l)
  $pid2 = 0
  [W]::GetWindowThreadProcessId($h, [ref]$pid2) | Out-Null
  if ($targets -contains $pid2) {
    $t = New-Object Text.StringBuilder 512
    $c = New-Object Text.StringBuilder 256
    [W]::GetWindowText($h,$t,512) | Out-Null
    [W]::GetClassName($h,$c,256) | Out-Null
    $script:found += ("pid=$pid2 vis=" + [W]::IsWindowVisible($h) + " class=" + $c.ToString() + " title=[" + $t.ToString() + "]")
  }
  return $true
}
[W]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
$found | ForEach-Object { Write-Output $_ }
Write-Output ("word-pids: " + ($targets -join ","))

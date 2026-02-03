# tools/start_ui.ps1
$ErrorActionPreference = "Stop"

$blender = "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
$bridge  = "D:\Torr\ui_bridge_tcp.py"
$ping    = "D:\Torr\tools\ui_ping.py"

Write-Host "== Torr: starting Blender UI + bridge =="

Start-Process -FilePath $blender -ArgumentList @("--python", $bridge) | Out-Null

Start-Sleep -Seconds 2

Write-Host "== Torr: ping UI bridge =="
python $ping

Write-Host "== OK: UI bridge ready on 127.0.0.1:61888 =="

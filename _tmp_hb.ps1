$j = Get-Content 'C:/Users/yiseg/.qclaw/workspace/memory/heartbeat-state.json' | ConvertFrom-Json
$j.rotationIndex = 3
$j.lastTodoCheck = '2026-05-21 07:19'
$j.last_check = '2026-05-21 07:19'
($j | ConvertTo-Json -Depth 10) | Set-Content 'C:/Users/yiseg/.qclaw/workspace/memory/heartbeat-state.json' -Encoding UTF8

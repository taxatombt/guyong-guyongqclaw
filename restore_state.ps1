$state = @{
    lastTask = "evolver_check"
    lastCheck = Get-Date -Format "yyyy-MM-dd HH:mm"
    issues = @{
        evolver = "No new learning today (2026-05-31). Most recent rule: 2026-05-10 Viki LLM集成"
        todos_= "_Checked 2026 -30.md and"..."
        python_= "..."
    }
    nextTask = "todo_check"
}

$json = $state | ConvertTo-Json -Depth 3
Set-Content -Path "C:/Users/yiseg/.qclaw/workspace/memory/heartbeat-state.json" -Value $json -Encoding UTF8
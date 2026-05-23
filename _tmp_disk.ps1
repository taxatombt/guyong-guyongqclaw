Get-PSDrive C,D,E,F -PSProvider FileSystem | ForEach-Object {
    $pct = [math]::Round($_.Free / ($_.Used + $_.Free) * 100, 1)
    $free = [math]::Round($_.Free / 1GB, 1)
    $total = [math]::Round(($_.Used + $_.Free) / 1GB, 1)
    Write-Output "$($_.Name): ${free}GB free of ${total}GB (${pct}%)"
}

Get-PSDrive -PSProvider FileSystem | ForEach-Object {
    [PSCustomObject]@{
        Name = $_.Name
        UsedGB = [math]::Round($_.Used / 1GB, 2)
        FreeGB = [math]::Round($_.Free / 1GB, 2)
        FreePct = [math]::Round($_.Free / ($_.Used + $_.Free) * 100, 1)
    }
} | Format-Table -AutoSize

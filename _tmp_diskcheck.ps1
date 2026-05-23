Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DeviceID -match '^[CDEF]:' } | ForEach-Object {
    $total = [math]::Round($_.Size/1GB,0)
    $free = [math]::Round($_.FreeSpace/1GB,0)
    $pct = [math]::Round($_.FreeSpace/$_.Size*100,1)
    Write-Host "$($_.DeviceID) Total=${total}GB Free=${free}GB (${pct}%)"
}

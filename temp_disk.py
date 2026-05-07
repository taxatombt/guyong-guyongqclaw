# -*- coding: utf-8 -*-
import psutil
parts = psutil.disk_partitions()
for p in parts:
    if p.fstype and p.device:
        try:
            u = psutil.disk_usage(p.mountpoint)
            pct = u.percent
            flag = '⚠️' if pct > 95 else ('🚨' if pct > 99 else '✅')
            print(f"{p.device} {u.free/1e9:.1f}GB({100-pct:.1f}%free){flag}")
        except: pass

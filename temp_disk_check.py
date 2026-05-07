import shutil
for d in ['C:\\', 'D:\\', 'E:\\', 'F:\\']:
    u = shutil.disk_usage(d)
    print(f"{d[0]}: {u.free/1e9:.1f}GB ({u.free/u.total*100:.1f}%)")

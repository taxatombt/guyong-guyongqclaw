import sys
sys.path.insert(0, r'C:\Users\yiseg\.qclaw\workspace')
from heartbeat_self_review import check_and_remind
result = check_and_remind()
print(result if result else "No reminder needed")

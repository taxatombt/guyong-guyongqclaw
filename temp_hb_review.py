import sys, os
sys.path.insert(0, r'C:\Users\yiseg\.qclaw\workspace')
import heartbeat_self_review

result = heartbeat_self_review.check_and_remind()
print(result if result else "NO_REVIEW_NEEDED")
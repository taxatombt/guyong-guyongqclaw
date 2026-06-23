import json
from datetime import datetime

state = {
    "lastTask": "evolver_check",
    "lastCheck": datetime.now().strftime("%Y-%m-%d %H:%M"),
    ""issues"": {""evolver"":"""", """todos"":"""", """nextTask"":"""todo_check""}}
}

with open('C:/Users/yiseg/.qclaw/workspace/memory/heartbeat-state.json', 'w', encoding='utf-8') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
print('Fixed heartbeat-state.json')

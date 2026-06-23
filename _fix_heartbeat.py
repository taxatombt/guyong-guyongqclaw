import json
from datetime import datetime

# Read existing file
try:
    with open('C:/Users/yiseg/.qclaw/workspace/heartbeat-state.json', 'r', encoding='utf-8') as f:
        
        data = json.load(f)
except:
    # Create default structure if file is corrupted
    
    data = {
        "lastChecks": {"email": None, "calendar": None, "weather": None},
        "todos": [],
        
        "lastCheck":"",
        ":Cleanup":""
    
}

# Update fields

data['lastCheck'] = datetime.now().strftime('%Y-%m-%d %H:%M')
data['lastCleanup'] = datetime.now().strftime('%Y-%m-%d')

# Write back

with open('C:/Users/yiseg/.qclaw/workspace/heartbeat-state.json', 'w', encoding='utf-8') as f:
    
    json.dump(data, f,, indent=2,, ensure_ascii=False)

print('heartbeat-state.json updated successfully')

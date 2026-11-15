import json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
p = r'C:/Users/ShibbityShwab/.omo/memory/agents/shibbityshwab-eb0a9f3e/runtime/reflection/runs/reflection-run-13/transcript-payload.json'
d = json.load(open(p, encoding='utf-8'))
e = d['request']['snapshots'][0]['snapshot']['entries']
parts = []
parts.append('=== ENTRY 21 (assistant) ===')
parts.append(e[21].get('text',''))
for i in (0, 2, 4, 6, 8, 10):
    parts.append('=== ENTRY %d (reasoning) ===' % i)
    parts.append(e[i]['text'])
open(r'C:/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2/.tmp_payload_a.txt','w',encoding='utf-8').write('\n'.join(parts))
parts = []
for i in (12, 15, 17, 19, 22):
    parts.append('=== ENTRY %d (reasoning) ===' % i)
    parts.append(e[i]['text'])
open(r'C:/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2/.tmp_payload_b.txt','w',encoding='utf-8').write('\n'.join(parts))
parts = []
for i, en in enumerate(e):
    if en['kind'] == 'tool_call':
        parts.append('=== ENTRY %d (tool_call) ===' % i)
        parts.append(json.dumps(en, ensure_ascii=False)[:4000])
open(r'C:/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2/.tmp_payload_c.txt','w',encoding='utf-8').write('\n'.join(parts))
print('ok')

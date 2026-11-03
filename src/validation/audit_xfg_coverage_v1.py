#!/usr/bin/env python3
"""Read-only audit of NBA shot-event CSV versus xFG JSONs, by event and player."""
import csv, json
from pathlib import Path
from collections import defaultdict, Counter

home=Path.home()/ 'Downloads'
reference=home/'nba_2025_26_all_shot_events.csv'
game_dir=home/'nba_xfg_output/games'
out=home/'xfg_coverage_audit_v1'
if not reference.is_file() or not game_dir.is_dir():
    raise SystemExit(f'Missing required input: {reference} or {game_dir}')
out.mkdir(exist_ok=True)

def norm_id(v):
    s=str(v or '').strip()
    if not s: return ''
    try: return str(int(float(s)))
    except (ValueError, OverflowError): return s

def game_id(v):
    s=norm_id(v)
    return s.zfill(10) if s else ''

def write_csv(name,rows,fields):
    with (out/name).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)

reference_events=defaultdict(dict)
reference_players=defaultdict(lambda: defaultdict(set))
ref_duplicates=0
with reference.open(newline='',encoding='utf-8-sig') as f:
    reader=csv.DictReader(f)
    required={'GAME_ID','GAME_EVENT_ID','PLAYER_ID'}
    if not required.issubset(reader.fieldnames or []):
        raise SystemExit(f'Reference CSV missing {required-set(reader.fieldnames or [])}; found {reader.fieldnames}')
    for r in reader:
        gid=game_id(r['GAME_ID']); event=norm_id(r['GAME_EVENT_ID']); pid=norm_id(r['PLAYER_ID'])
        if not gid or not event: continue
        if event in reference_events[gid]:
            ref_duplicates+=1
            continue
        reference_events[gid][event]=r
        reference_players[gid][pid].add(event)

summary=[]; missing=[]; extra=[]; players=[]; duplicates=[]
for path in sorted(game_dir.glob('00225*.json')):
    gid=path.stem
    try: data=json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        summary.append({'game_id':gid,'error':str(e)}); continue
    shots=data.get('shots',[])
    if not isinstance(shots,list):
        summary.append({'game_id':gid,'error':'shots is not a list'}); continue
    xfg=defaultdict(list)
    for i,s in enumerate(shots):
        if not isinstance(s,dict): continue
        event=norm_id(s.get('eventNum'))
        if event: xfg[event].append((i,s))
    ref=reference_events.get(gid,{})
    ref_keys=set(ref); xfg_keys=set(xfg)
    common=ref_keys & xfg_keys
    player_mismatches=0
    for event in common:
        rp=norm_id(ref[event].get('PLAYER_ID'))
        xp={norm_id(s.get('playerId')) for _,s in xfg[event]}
        if rp and rp not in xp: player_mismatches+=1
    for event in sorted(ref_keys-xfg_keys,key=lambda x:int(x) if x.isdigit() else x):
        r=ref[event]
        missing.append({'game_id':gid,'event_num':event,'player_id':norm_id(r.get('PLAYER_ID')),
                        'player_name':r.get('PLAYER_NAME',''),'period':r.get('PERIOD',''),
                        'game_date':r.get('GAME_DATE',''),'home':r.get('HTM',''),'away':r.get('VTM','')})
    for event in sorted(xfg_keys-ref_keys,key=lambda x:int(x) if x.isdigit() else x):
        s=xfg[event][0][1]
        extra.append({'game_id':gid,'event_num':event,'player_id':norm_id(s.get('playerId')),
                      'player_name':s.get('playerName',''),'period':s.get('period','')})
    for event,items in xfg.items():
        if len(items)>1:
            duplicates.append({'game_id':gid,'event_num':event,'observations':len(items),
                               'xfg_values':' | '.join(str(s.get('shotQuality')) for _,s in items),
                               'success_values':' | '.join(str(s.get('success')) for _,s in items)})
    pids=set(reference_players.get(gid,{})) | {norm_id(s.get('playerId')) for items in xfg.values() for _,s in items}
    for pid in sorted(pids):
        rkeys=reference_players.get(gid,{}).get(pid,set())
        xkeys={event for event,items in xfg.items() if any(norm_id(s.get('playerId'))==pid for _,s in items)}
        if rkeys-xkeys or xkeys-rkeys:
            name=next((r.get('PLAYER_NAME','') for event,r in ref.items() if norm_id(r.get('PLAYER_ID'))==pid),'')
            if not name: name=next((s.get('playerName','') for items in xfg.values() for _,s in items if norm_id(s.get('playerId'))==pid),'')
            players.append({'game_id':gid,'player_id':pid,'player_name':name,'reference_fga':len(rkeys),
                            'xfg_unique_events':len(xkeys),'missing_reference_events':len(rkeys-xkeys),
                            'extra_xfg_events':len(xkeys-rkeys)})
    summary.append({'game_id':gid,'reference_fga':len(ref_keys),'xfg_raw_records':len(shots),
                    'xfg_unique_events':len(xfg_keys),'matched_event_keys':len(common),
                    'missing_xfg_events':len(ref_keys-xfg_keys),'extra_xfg_events':len(xfg_keys-ref_keys),
                    'player_id_mismatches':player_mismatches,
                    'duplicate_excess':sum(len(v)-1 for v in xfg.values()),'error':''})

write_csv('game_coverage.csv',summary,['game_id','reference_fga','xfg_raw_records','xfg_unique_events','matched_event_keys','missing_xfg_events','extra_xfg_events','player_id_mismatches','duplicate_excess','error'])
write_csv('missing_shots.csv',missing,['game_id','event_num','player_id','player_name','period','game_date','home','away'])
write_csv('extra_xfg_shots.csv',extra,['game_id','event_num','player_id','player_name','period'])
write_csv('player_gaps.csv',players,['game_id','player_id','player_name','reference_fga','xfg_unique_events','missing_reference_events','extra_xfg_events'])
write_csv('duplicate_events.csv',duplicates,['game_id','event_num','observations','xfg_values','success_values'])
report={'reference_games':len(reference_events),'xfg_games':len(summary),
        'reference_unique_fga':sum(map(len,reference_events.values())),
        'reference_duplicate_event_rows':ref_duplicates,
        'xfg_raw_records':sum(int(r.get('xfg_raw_records') or 0) for r in summary),
        'matched_event_keys':sum(int(r.get('matched_event_keys') or 0) for r in summary),
        'missing_xfg_events':len(missing),'extra_xfg_events':len(extra),
        'player_id_mismatches':sum(int(r.get('player_id_mismatches') or 0) for r in summary),
        'games_with_missing_xfg':sum(int(r.get('missing_xfg_events') or 0)>0 for r in summary),
        'games_with_extra_xfg':sum(int(r.get('extra_xfg_events') or 0)>0 for r in summary),
        'note':'Reference CSV is an independent shot-event comparison, not yet confirmed complete or official FGA truth. Event key matches are not full shot validation.'}
(out/'summary.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
print('\n20 largest missing-shot games:')
for r in sorted(summary,key=lambda r:int(r.get('missing_xfg_events') or 0),reverse=True)[:20]:
    print(r['game_id'],'missing',r.get('missing_xfg_events',0),'of',r.get('reference_fga',0),'xfg',r.get('xfg_unique_events',0))
print('\nSaved:',out)

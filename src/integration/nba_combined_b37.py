from pathlib import Path
import csv,json,collections
D=Path.home()/'Downloads'; B=D/'nba_espn_xfg_integration_v1'; O=B/'combined_analytics_b37'; O.mkdir(parents=True,exist_ok=True)
ids=['0022500062','0022500147','0022500296','0022500537','0022500651','0022500652','0022500716','0022500717','0022500718','0022500720','0022500721','0022500723','0022500724','0022500725','0022500867']; wanted=set(ids)
inputs=[D/'nba_2025_26_shot_types'/'nba_2025_26_all_shot_events_complete.csv',D/'nba_2025_26_shot_types'/'shots_2025-11.csv',D/'pih_canonical_v2'/'canonical_shots_v2.csv']
report=[]
for p in inputs:
 if not p.exists():report.append({'file':str(p),'status':'MISSING'});continue
 try:
  with p.open(encoding='utf-8-sig',newline='') as f:
   reader=csv.DictReader(f); fields=reader.fieldnames or []; gamecols=[c for c in fields if ('game' in c.lower() and ('id' in c.lower() or c.lower()=='game'))]; counts=collections.Counter(); examples={}
   for row in reader:
    for c in gamecols:
     v=str(row.get(c,'')).strip(); v=v.zfill(10) if v.isdigit() else v
     if v in wanted:counts[v]+=1;examples.setdefault(v,{k:row[k] for k in fields[:18]})
  report.append({'file':str(p),'status':'OK','game_columns':gamecols,'fields':fields,'counts':dict(counts),'example':next(iter(examples.values()),{})})
 except Exception as e:report.append({'file':str(p),'status':'ERROR','error':str(e)})
json_report=[]
for g in ids:
 for p in [D/'nba_xfg_output'/'games'/f'{g}.json',D/'nba_xfg_repair'/f'{g}.json',D/'nba_xfg_repair_test'/f'{g}.json']:
  if not p.exists():continue
  try:
   data=json.loads(p.read_text(encoding='utf-8-sig')); top=list(data)[:35] if isinstance(data,dict) else []; keys=collections.Counter(); samples=[]
   def walk(x,depth=0):
    if depth>10:return
    if isinstance(x,dict):
     keys.update(x.keys());
     if len(samples)<2 and any('shot' in str(v).lower() for k,v in x.items() if k.lower() in ('type','event_type','actiontype','action_type','description')):samples.append({k:str(v)[:150] for k,v in list(x.items())[:18]})
     for v in x.values():walk(v,depth+1)
    elif isinstance(x,list):
     for v in x[:300]:walk(v,depth+1)
   walk(data)
   json_report.append({'game':g,'file':str(p),'bytes':p.stat().st_size,'top_keys':top,'frequent_keys':keys.most_common(35),'shot_samples':samples})
  except Exception as e:json_report.append({'game':g,'file':str(p),'error':str(e)})
(O/'b37_source_schema_report.json').write_text(json.dumps({'csv_sources':report,'json_sources':json_report},indent=2,ensure_ascii=False))
print('=== B37 SOURCE STRUCTURE AND RECOVERY TRIAGE ===')
for r in report:
 print('CSV:',Path(r['file']).name,'status:',r['status'],'game_columns:',r.get('game_columns'),'missing-game rows:',sum(r.get('counts',{}).values()))
 print(' counts:',r.get('counts',{}));print(' fields:',r.get('fields',[])[:30]);print(' example:',str(r.get('example',{}))[:500])
print('JSON source files:',len(json_report))
for r in json_report[:5]:print(r['game'],Path(r['file']).parent.name,'bytes:',r.get('bytes'),'top_keys:',r.get('top_keys'),'shot_samples:',str(r.get('shot_samples'))[:400])
print('Report:',O/'b37_source_schema_report.json');print('=== B37 COMPLETE ===')

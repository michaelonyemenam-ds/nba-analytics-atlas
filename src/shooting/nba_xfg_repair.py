#!/usr/bin/env python3
"""Safely retry empty/incomplete NBA.com xFG games into a separate directory."""
import argparse, json, time, random, urllib.request, urllib.parse, urllib.error
from pathlib import Path

BASE='https://stats.nba.com/stats/'
HEADERS={'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/18.3 Safari/605.1.15','Referer':'https://www.nba.com/','Origin':'https://www.nba.com','Accept':'application/json, text/plain, */*'}

def fetch(endpoint, params, retries=2):
    url=BASE+endpoint+'?'+urllib.parse.urlencode(params)
    for attempt in range(retries+1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=HEADERS),timeout=25) as r:
                return json.load(r)
        except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,json.JSONDecodeError) as e:
            code=getattr(e,'code',None)
            if code in (401,403,404,429) or attempt==retries:
                raise RuntimeError(f'{endpoint}: {e}') from e
            time.sleep(3*(attempt+1))

def players_from_boxscore(data):
    box=data.get('boxScoreTraditional',{})
    result=[]
    for side in ('homeTeam','awayTeam'):
        team=box.get(side,{})
        for p in team.get('players',[]):
            fga=(p.get('statistics') or {}).get('fieldGoalsAttempted',0) or 0
            if fga>0:
                result.append((p['personId'],team.get('teamTricode') or side,fga,p.get('name') or p.get('nameI') or ''))
    if not result: raise ValueError('No players with FGA in boxscore')
    return result

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',default=str(Path.home()/'Downloads/nba_xfg_output/games'))
    ap.add_argument('--output',default=str(Path.home()/'Downloads/nba_xfg_repair'))
    ap.add_argument('--limit',type=int,default=1)
    ap.add_argument('--delay',type=float,default=1.5)
    ap.add_argument('--mode',choices=['empty','incomplete'],default='empty')
    args=ap.parse_args()
    root=Path(args.root); out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    targets=[]
    for path in sorted(root.glob('00225*.json')):
        data=json.loads(path.read_text())
        if args.mode=='empty':
            selected=not data.get('shots')
        else:
            selected=bool(data.get('shots')) and any((r.get('status')!='ok' or (r.get('missing') or 0)>0) for r in data.get('coverage',[]))
        if selected and not (out/path.name).exists(): targets.append(path)
    print(f'Mode: {args.mode}; outstanding targets: {len(targets)}',flush=True)
    for path in targets[:args.limit]:
        original=json.loads(path.read_text()); gid=str(original['gameId'])
        print(f'Game {gid}',flush=True)
        try: players=players_from_boxscore(fetch('boxscoretraditionalv3',{'GameID':gid,'LeagueID':'00'}))
        except Exception as e:
            print(f'  Boxscore error: {e}; stopping batch',flush=True); break
        shots=[]; coverage=[]; access_stop=False
        for i,(pid,team,fga,name) in enumerate(players,1):
            time.sleep(args.delay+random.uniform(0,.4))
            try:
                data=fetch('shotqualityvideologs',{'GameID':gid,'PlayerID':pid})
                player_shots=data.get('shotList')
                if not isinstance(player_shots,list): raise ValueError('Missing shotList')
                shots.extend({'gameId':gid,'playerId':pid,'playerName':data.get('playerName') or name,'team':team,**shot} for shot in player_shots)
                status='ok'
            except Exception as e:
                player_shots=[]; status=str(e)
                print(f'  {i}/{len(players)} {name}: {status}',flush=True)
                if any(f'HTTP Error {code}' in status for code in (401,403,429)):
                    access_stop=True
            else: print(f'  {i}/{len(players)} {name}: {len(player_shots)} shots',flush=True)
            coverage.append({'playerId':pid,'playerName':name,'team':team,'fga':fga,'xfgShots':len(player_shots),'missing':fga-len(player_shots),'status':status})
            if access_stop: break
        if access_stop:
            print('Access/rate limit detected. Stopping without writing incomplete repair.',flush=True); break
        dest=out/path.name
        tmp=dest.with_suffix('.tmp')
        tmp.write_text(json.dumps({'gameId':gid,'shots':shots,'coverage':coverage},ensure_ascii=False,indent=2))
        tmp.replace(dest)
        print(f'  Saved separate repair: {dest} ({len(shots)} shots)',flush=True)
        if not shots:
            print('  Still empty; check NBA.com source availability.',flush=True)
    print('Original archive was not modified.',flush=True)
if __name__=='__main__': main()

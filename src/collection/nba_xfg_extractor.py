#!/usr/bin/env python3
"""Checkpointed NBA 2025-26 shot-quality collector. Uses public NBA stats endpoints.
Run with --limit 1 initially. Respect server errors/rate limits.
"""
import argparse, csv, json, random, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

BASE = 'https://stats.nba.com/stats/'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/18.3 Safari/605.1.15',
    'Referer': 'https://www.nba.com/', 'Origin': 'https://www.nba.com',
    'Accept': 'application/json, text/plain, */*',
}

def fetch(endpoint, params, retries=2):
    url = BASE + endpoint + '?' + urllib.parse.urlencode(params)
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=25) as r:
                return json.load(r)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            status = getattr(e, 'code', None)
            if status in (401, 403, 404):
                raise RuntimeError(f'{endpoint}: HTTP {status} (access denied or unavailable)') from e
            if attempt == retries:
                raise RuntimeError(f'{endpoint}: {e}') from e
            time.sleep(min(15, 3 * (attempt + 1)))

def players_from_boxscore(data):
    box = data.get('boxScoreTraditional', {})
    players = []
    for side in ('homeTeam', 'awayTeam'):
        team = box.get(side, {})
        team_label = team.get('teamTricode') or team.get('teamName') or side
        for p in team.get('players', []):
            stats = p.get('statistics') or {}
            fga = stats.get('fieldGoalsAttempted', 0) or 0
            if fga > 0:
                players.append((p['personId'], team_label, fga, p.get('name') or p.get('nameI') or ''))
    if not players:
        raise ValueError('Box score contained no players with FGA; inspect response structure')
    return players

def save_json_atomic(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--games', default='nba_2025_26_season_game_ids.json')
    parser.add_argument('--output', default='nba_xfg_output')
    parser.add_argument('--limit', type=int, default=1, help='Number of unprocessed games to attempt (default: 1)')
    parser.add_argument('--delay', type=float, default=1.5, help='Minimum seconds between player requests')
    args = parser.parse_args()
    source = json.loads(Path(args.games).read_text(encoding='utf-8'))
    game_ids = source['gameIds']
    if len(game_ids) != len(set(game_ids)):
        raise ValueError('Duplicate game IDs in input')
    out = Path(args.output)
    (out / 'games').mkdir(parents=True, exist_ok=True)
    attempts = 0
    for game_id in game_ids:
        dest = out / 'games' / f'{game_id}.json'
        if dest.exists():
            continue
        if attempts >= args.limit:
            break
        attempts += 1
        print(f'Game {game_id}: requesting box score...', flush=True)
        try:
            players = players_from_boxscore(fetch('boxscoretraditionalv3', {'GameID': game_id, 'LeagueID': '00'}))
        except Exception as e:
            print(f'  STOP: box score failed: {e}', flush=True)
            print('  No checkpoint written. Do not increase --limit until access is working.')
            break
        shots, coverage = [], []
        for i, (player_id, team, fga, name) in enumerate(players, 1):
            time.sleep(args.delay + random.uniform(0, 0.4))
            try:
                data = fetch('shotqualityvideologs', {'GameID': game_id, 'PlayerID': player_id})
                player_shots = data.get('shotList')
                if not isinstance(player_shots, list):
                    raise ValueError('Missing shotList')
                for shot in player_shots:
                    shots.append({'gameId': game_id, 'playerId': player_id, 'playerName': data.get('playerName') or name, 'team': team, **shot})
                coverage.append({'playerId': player_id, 'playerName': name, 'team': team, 'fga': fga, 'xfgShots': len(player_shots), 'missing': fga-len(player_shots), 'status': 'ok'})
            except Exception as e:
                coverage.append({'playerId': player_id, 'playerName': name, 'team': team, 'fga': fga, 'xfgShots': 0, 'missing': fga, 'status': str(e)})
                print(f'  {i}/{len(players)} {name}: {e}', flush=True)
                if '403' in str(e) or '429' in str(e):
                    print('  STOP: access/rate limit. Save partial game separately and retry later.', flush=True)
                    save_json_atomic(out / 'partial_game.json', {'gameId': game_id, 'shots': shots, 'coverage': coverage})
                    return
            else:
                print(f'  {i}/{len(players)} {name}: {len(player_shots)} shots', flush=True)
        save_json_atomic(dest, {'gameId': game_id, 'shots': shots, 'coverage': coverage})
        print(f'  CHECKPOINT: {len(shots)} shot records, {len(coverage)} player rows; {dest}', flush=True)
    print('Completed requested attempt(s). Run with --limit 10 only after checking the first result.')

if __name__ == '__main__':
    main()

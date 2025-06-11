import requests
import time
from collections import deque
import concurrent.futures
import pickle
import os

API_KEY = "RGAPI-90af0c5d-b9b8-4dd2-8f78-9bdcc602ce2b"
HEADERS = {"X-Riot-Token": API_KEY}
REGIONS = ["na1", "euw", "kr"]
V5_REGIONS = ["americas"]
TIERS = ["CHALLENGER"]
LEADERBOARD = "https://op.gg/lol/leaderboards/tier?region="


def get_players(region, tier, division, page):
    url = f"https://{region}.api.riotgames.com/lol/league-exp/v4/entries/RANKED_SOLO_5x5/{tier}/{division}?page={page}"
    response = requests.get(url, headers=HEADERS)
    return [entry["puuid"] for entry in response.json()]


def get_chall_players(region):
    url = f"https://{region}.api.riotgames.com/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5"
    response = requests.get(url, headers=HEADERS)
    return [entry["puuid"] for entry in response.json()["entries"]]

def get_gm_players(region):
    url = f"https://{region}.api.riotgames.com/lol/league/v4/grandmasterleagues/by-queue/RANKED_SOLO_5x5"
    response = requests.get(url, headers=HEADERS)
    return [entry["puuid"] for entry in response.json()["entries"]]

def get_master_players(region):
    url = f"https://{region}.api.riotgames.com/lol/league/v4/masterleagues/by-queue/RANKED_SOLO_5x5"
    response = requests.get(url, headers=HEADERS)
    return [entry["puuid"] for entry in response.json()["entries"]]

def get_match_ids(puuid, v5region, count=100):
    url = f"https://{v5region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    params = {"count": count, "queue": 420}  # 420 is solo queue

    try:
        response = requests.get(url, headers=HEADERS, params=params)

        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 1))
            print(f"Rate limited, Waiting {retry_after} seconds ...")
            time.sleep(retry_after + 1)
            return get_match_ids(puuid, v5region, count)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error: {response.status_code}: {response.text}")
            return []
        
    except Exception as e:
        print(f"Exception while fetching matches for {puuid}: {e}")

def collect_match_ids(players, v5region):
    """
    Gets a unique master list of matches for a region
    """

    unique_matches = set()
    total_players = len(players)
    processed = 0

    # checkpoint system for resuming
    CHECKPOINT_INTERVAL = 50
    CHECKPOINT_FILE = "match_ids_checkpoint.pk1"

    # load from checkpoint if it exists
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "rb") as f:
            saved_data = pickle.load(f)
            unique_matches = saved_data["matches"]
            processed = saved_data["processed"]
            players = players[processed:]
            print(f"Loaded checkpoint: {len(unique_matches)}, {processed} players processed")

    BATCH_SIZE = 10  # can adjust this based on rate limit
    
    for i in range(0, len(players), BATCH_SIZE):
        batch = players[i:i+BATCH_SIZE]
        batch_results = []

        # process batch with concurrent execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
            futures = {executor.submit(get_match_ids, puuid, v5region): puuid for puuid in batch}
            for future in concurrent.futures.as_completed(futures):
                batch_results.extend(future.result())

        # update unique matches
        unique_matches.update(batch_results)

        # update progress
        processed += len(batch)
        print(f"Processed {processed}/{total_players} players. Found {len(unique_matches)} unqiue matches.")

        # create checkpoint
        if processed % CHECKPOINT_INTERVAL == 0:
            with open(CHECKPOINT_FILE, "wb") as f:
                pickle.dump({"matches": unique_matches, "processed": processed}, f)
            print(f"Checkpoint created at {processed} players")

        time.sleep(1)


    return list(unique_matches)


def get_match_details(match_id, v5region):
    url = f"https://{v5region}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    response = requests.get(url, headers=HEADERS)
    return response.json()

def main():
    players = []
    # players.extend(get_players("na1", "CHALLENGER", "I", 1))
    # players.extend(get_players("na1", "CHALLENGER", "I", 2))
    # players = set(players)

    players.extend(get_chall_players("na1"))  # get all chall players
    players.extend(get_gm_players("na1"))  # get all gm players
    players.extend(get_master_players("na1"))  # get all master players

    print(len(players))

    match_ids = collect_match_ids(players, "americas")




main()
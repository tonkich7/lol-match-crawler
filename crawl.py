import requests

API_KEY = "RGAPI-90af0c5d-b9b8-4dd2-8f78-9bdcc602ce2b"
HEADERS = {"X-Riot-Token": API_KEY}
REGIONS = ["na1", "euw", "kr"]
TIERS = ["CHALLENGER"]
LEADERBOARD = "https://op.gg/lol/leaderboards/tier?region="


def get_players(region, tier, division, page):
    url = f"https://{region}.api.riotgames.com/lol/league-exp/v4/entries/RANKED_SOLO_5x5/{tier}/{division}?page={page}"
    response = requests.get(url, headers=HEADERS)
    return [entry["summonerId"] for entry in response.json()]


def get_chall_players(region):
    url = f"https://{region}.api.riotgames.com/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5"
    response = requests.get(url, headers=HEADERS)
    return [entry["summonerId"] for entry in response.json()["entries"]]

def get_gm_players(region):
    url = f"https://{region}.api.riotgames.com/lol/league/v4/grandmasterleagues/by-queue/RANKED_SOLO_5x5"
    response = requests.get(url, headers=HEADERS)
    return [entry["summonerId"] for entry in response.json()["entries"]]

def get_master_players(region):
    url = f"https://{region}.api.riotgames.com/lol/league/v4/masterleagues/by-queue/RANKED_SOLO_5x5"
    response = requests.get(url, headers=HEADERS)
    return [entry["summonerId"] for entry in response.json()["entries"]]

def main():
    players = []
    # players.extend(get_players("na1", "CHALLENGER", "I", 1))
    # players.extend(get_players("na1", "CHALLENGER", "I", 2))
    # players = set(players)

    players.extend(get_chall_players("na1"))  # get all chall players
    players.extend(get_gm_players("na1"))  # get all gm players
    players.extend(get_master_players("na1"))  # get all master players

    print(len(players))




main()
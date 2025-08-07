import requests
import time
from collections import deque
import concurrent.futures
import pickle
import os
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urljoin, urlparse
import urllib3
import random
from fake_useragent import UserAgent

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
REGIONS = ["na", "euw", "kr", "eune", "las", "lan", "oce", "tr", "ru", "jp", "br"]
TIERS = ["challenger", "grandmaster", "master", "diamond", "emerald", "platinum"]
BASE_URL = "https://www.op.gg"

# Checkpoint system
CHECKPOINT_INTERVAL = 25
CHECKPOINT_FILE = "opgg_data_checkpoint.pkl"

# Initialize fake user agent
ua = UserAgent()

def get_random_headers():
    """Generate random headers to avoid detection"""
    headers = {
        'User-Agent': ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Charset': 'utf-8',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0',
        'DNT': '1',
        'Pragma': 'no-cache'
    }
    return headers

# Create session with rotating user agents
session = requests.Session()
session.verify = False

def safe_request(url, retries=3, **kwargs):
    """Make a safe request with anti-detection measures"""
    for attempt in range(retries):
        try:
            # Rotate headers for each request
            session.headers.update(get_random_headers())
            
            # Add random delay between requests
            time.sleep(random.uniform(2, 5))
            
            kwargs['verify'] = False
            kwargs['timeout'] = 30
            kwargs['allow_redirects'] = True
            
            response = session.get(url, **kwargs)
            
            if response.status_code == 200:
                return response
            elif response.status_code == 403:
                print(f"403 Forbidden for {url} (attempt {attempt + 1})")
                if attempt < retries - 1:
                    wait_time = random.uniform(10, 20) * (attempt + 1)
                    print(f"Waiting {wait_time:.1f} seconds before retry...")
                    time.sleep(wait_time)
                    continue
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 30))
                print(f"Rate limited, waiting {retry_after} seconds...")
                time.sleep(retry_after + random.uniform(5, 15))
                continue
            else:
                print(f"HTTP {response.status_code} for {url}")
                
        except requests.exceptions.SSLError as e:
            print(f"SSL Error: {e}")
            kwargs['verify'] = False
        except Exception as e:
            print(f"Request error (attempt {attempt + 1}): {e}")
            if attempt < retries - 1:
                time.sleep(random.uniform(5, 10))
    
    return None

def try_alternative_urls(region, tier, page=1):
    """Try different URL formats for OP.GG"""
    urls_to_try = [
        f"https://www.op.gg/leaderboards/tier?region={region}&tier={tier}&page={page}",
        f"https://op.gg/leaderboards/tier?region={region}&tier={tier}&page={page}",
        f"https://www.op.gg/lol/leaderboards/tier?region={region}&tier={tier}&page={page}",
        f"https://na.op.gg/leaderboards?type=soloranked&tier={tier}" if region == "na" else None,
        f"https://www.op.gg/ranking/ladder/page={page}",
    ]
    
    # Filter out None values
    urls_to_try = [url for url in urls_to_try if url]
    
    for url in urls_to_try:
        print(f"Trying URL: {url}")
        response = safe_request(url)
        if response and response.status_code == 200:
            print(f"✓ Success with URL: {url}")
            return response
        else:
            print(f"✗ Failed with URL: {url}")
    
    return None

def get_leaderboard_players(region, tier="challenger", page=1):
    """
    Scrape players from OP.GG leaderboards with multiple fallback methods
    """
    print(f"Fetching {tier} players for {region}...")
    
    # Try different URL formats
    response = try_alternative_urls(region, tier, page)
    
    if not response:
        print(f"All URL attempts failed for {region} {tier}")
        return []
    
    try:
        soup = BeautifulSoup(response.content, 'html.parser')
        players = []
        
        print(f"Successfully loaded page for {region} {tier}")
        
        # Debug: Print page title to see what we got
        title = soup.find('title')
        if title:
            print(f"Page title: {title.get_text()}")
        
        # Multiple approaches to find player data
        approaches = [
            extract_from_table,
            extract_from_links,
            extract_from_json,
            extract_from_divs
        ]
        
        for approach in approaches:
            try:
                found_players = approach(soup, region, tier)
                if found_players:
                    players.extend(found_players)
                    print(f"✓ Found {len(found_players)} players using {approach.__name__}")
                    break
            except Exception as e:
                print(f"✗ {approach.__name__} failed: {e}")
                continue
        
        return players[:50]  # Limit to reasonable number
        
    except Exception as e:
        print(f"Exception while parsing leaderboard for {region}-{tier}: {e}")
        return []

def extract_from_table(soup, region, tier):
    """Extract players from table structure"""
    players = []
    
    # Look for tables
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for row in rows[1:]:  # Skip header
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                # Look for player name in cells
                for cell in cells:
                    text = cell.get_text(strip=True)
                    links = cell.find_all('a', href=True)
                    
                    for link in links:
                        if any(keyword in link['href'] for keyword in ['summoner', 'profile', 'player']):
                            players.append({
                                'name': link.get_text(strip=True) or text,
                                'url': urljoin(BASE_URL, link['href']),
                                'region': region,
                                'tier': tier
                            })
    
    return players

def extract_from_links(soup, region, tier):
    """Extract players from links"""
    players = []
    
    # Find all links that might be player profiles
    selectors = [
        'a[href*="summoner"]',
        'a[href*="profile"]',
        'a[href*="player"]',
        '.summoner-link',
        '.player-name a',
        '.ranking-table a'
    ]
    
    for selector in selectors:
        elements = soup.select(selector)
        if elements:
            for element in elements[:30]:
                name = element.get_text(strip=True)
                if name and len(name) > 2:
                    players.append({
                        'name': name,
                        'url': urljoin(BASE_URL, element['href']),
                        'region': region,
                        'tier': tier
                    })
            break
    
    return players

def extract_from_json(soup, region, tier):
    """Extract players from embedded JSON"""
    players = []
    
    scripts = soup.find_all('script')
    for script in scripts:
        if script.string:
            # Look for JSON with player data
            if any(keyword in script.string.lower() for keyword in ['summoner', 'player', 'ranking']):
                # Try to extract JSON
                json_patterns = [
                    r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
                    r'window\.__NUXT__\s*=\s*({.*?});',
                    r'var\s+data\s*=\s*({.*?});',
                    r'"summoners":\s*(\[.*?\])',
                    r'"players":\s*(\[.*?\])'
                ]
                
                for pattern in json_patterns:
                    matches = re.findall(pattern, script.string, re.DOTALL)
                    for match in matches:
                        try:
                            data = json.loads(match)
                            # Extract player info from JSON
                            extracted = extract_players_from_json(data, region, tier)
                            if extracted:
                                players.extend(extracted)
                                return players
                        except:
                            continue
    
    return players

def extract_from_divs(soup, region, tier):
    """Extract players from div structures"""
    players = []
    
    # Look for common div patterns
    patterns = [
        {'class': re.compile(r'summoner|player|ranking', re.I)},
        {'data-summoner-name': True},
        {'data-player': True}
    ]
    
    for pattern in patterns:
        elements = soup.find_all('div', pattern)
        for element in elements[:20]:
            # Look for name and link within the div
            link = element.find('a', href=True)
            if link and any(keyword in link['href'] for keyword in ['summoner', 'profile']):
                name = link.get_text(strip=True) or element.get_text(strip=True)
                if name:
                    players.append({
                        'name': name,
                        'url': urljoin(BASE_URL, link['href']),
                        'region': region,
                        'tier': tier
                    })
    
    return players

def extract_players_from_json(data, region, tier):
    """Extract player information from JSON data"""
    players = []
    
    def recursive_search(obj, players_list):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key.lower() in ['summoner', 'player', 'name', 'summoners', 'players']:
                    if isinstance(value, str) and len(value) > 2:
                        players_list.append({
                            'name': value,
                            'url': f"{BASE_URL}/summoners/{region}/{value.replace(' ', '%20')}",
                            'region': region,
                            'tier': tier
                        })
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict) and 'name' in item:
                                players_list.append({
                                    'name': item['name'],
                                    'url': f"{BASE_URL}/summoners/{region}/{item['name'].replace(' ', '%20')}",
                                    'region': region,
                                    'tier': tier
                                })
                recursive_search(value, players_list)
        elif isinstance(obj, list):
            for item in obj:
                recursive_search(item, players_list)
    
    recursive_search(data, players)
    return players

def get_chall_players(region):
    """Get challenger players"""
    return get_leaderboard_players(region, "challenger")

def get_gm_players(region):
    """Get grandmaster players"""
    return get_leaderboard_players(region, "grandmaster")

def get_master_players(region):
    """Get master players"""
    return get_leaderboard_players(region, "master")

def test_connection():
    """Test connection with multiple endpoints"""
    test_urls = [
        "https://www.op.gg",
        "https://op.gg",
        "https://www.op.gg/statistics/champions"
    ]
    
    for url in test_urls:
        try:
            response = safe_request(url)
            if response and response.status_code == 200:
                print(f"✓ Successfully connected to {url}")
                return True
            else:
                print(f"✗ Failed to connect to {url}")
        except Exception as e:
            print(f"✗ Connection test failed for {url}: {e}")
    
    return False

def main():
    """Main execution function"""
    print("Testing connection to OP.GG...")
    if not test_connection():
        print("Warning: Connection issues detected, but proceeding anyway...")
    
    players = []
    
    # Try to collect players from different tiers
    tiers_to_try = ["challenger", "grandmaster", "master"]
    
    for tier in tiers_to_try:
        print(f"\nCollecting {tier} players...")
        try:
            tier_players = get_leaderboard_players("na", tier)
            players.extend(tier_players)
            print(f"Found {len(tier_players)} {tier} players")
            
            # Add delay between tiers
            time.sleep(random.uniform(5, 10))
            
        except Exception as e:
            print(f"Error collecting {tier} players: {e}")
            continue
    
    # Remove duplicates
    unique_players = {player['url']: player for player in players}.values()
    players = list(unique_players)
    
    print(f"\nFound {len(players)} unique players total")
    
    if len(players) == 0:
        print("No players found. OP.GG might be blocking requests or structure has changed.")
        print("Consider using a VPN or proxy, or try again later.")
        return
    
    # Save the player list
    with open("opgg_players_found.json", "w", encoding='utf-8') as f:
        json.dump(players, f, indent=2, ensure_ascii=False)
    
    print("Player list saved to opgg_players_found.json")
    print("You can now analyze this data or continue with detailed scraping.")

if __name__ == "__main__":
    # Install required package
    try:
        from fake_useragent import UserAgent
    except ImportError:
        print("Installing fake-useragent...")
        os.system("pip install fake-useragent")
        from fake_useragent import UserAgent
    
    main()
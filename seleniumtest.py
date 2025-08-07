import time
import json
import pickle
import os
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
import concurrent.futures
from collections import deque

# Configuration
REGIONS = ["na", "euw", "kr"]
TIERS = ["challenger", "grandmaster", "master"]
BASE_URL = "https://www.op.gg"

# Checkpoint system
CHECKPOINT_INTERVAL = 25
CHECKPOINT_FILE = "opgg_selenium_checkpoint.pkl"

def setup_driver(headless=False):
    """Setup Chrome driver with anti-detection measures"""
    chrome_options = Options()
    
    if headless:
        chrome_options.add_argument("--headless")
    
    # Anti-detection measures
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins-discovery")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--allow-running-insecure-content")
    
    # Random user agent
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        
        # Execute script to hide webdriver property
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
    except Exception as e:
        print(f"Error setting up Chrome driver: {e}")
        print("Make sure you have Chrome and chromedriver installed")
        print("Install with: pip install selenium")
        print("Download chromedriver from: https://chromedriver.chromium.org/")
        return None

def human_like_delay():
    """Add human-like delays"""
    time.sleep(random.uniform(2, 5))

def scroll_page(driver):
    """Scroll page like a human"""
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
    time.sleep(random.uniform(1, 2))
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
    time.sleep(random.uniform(1, 2))
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(random.uniform(1, 2))

def get_leaderboard_players_selenium(driver, region, tier="challenger"):
    """
    Scrape players using Selenium
    """
    players = []
    
    # Try different URL formats
    urls_to_try = [
        f"https://www.op.gg/leaderboards/tier?region={region}&tier={tier}",
        f"https://op.gg/leaderboards/tier?region={region}&tier={tier}",
        f"https://www.op.gg/lol/leaderboards/tier?region={region}&tier={tier}",
    ]
    
    for url in urls_to_try:
        try:
            print(f"Trying URL: {url}")
            driver.get(url)
            human_like_delay()
            
            # Check if page loaded successfully
            if "403" in driver.title or "Forbidden" in driver.page_source:
                print(f"403 Forbidden for {url}")
                continue
            
            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            print(f"Page title: {driver.title}")
            
            # Scroll to load dynamic content
            scroll_page(driver)
            
            # Try multiple selectors to find player elements
            selectors = [
                "a[href*='summoner']",
                "a[href*='summoners']", 
                ".summoner-link",
                ".player-name a",
                ".ranking-table a",
                "[data-summoner-name]",
                ".leaderboard-table a",
                "tbody tr a"
            ]
            
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        print(f"Found {len(elements)} elements with selector: {selector}")
                        
                        for element in elements[:50]:  # Limit to 50
                            try:
                                name = element.text.strip()
                                href = element.get_attribute('href')
                                
                                if name and href and len(name) > 1:
                                    players.append({
                                        'name': name,
                                        'url': href,
                                        'region': region,
                                        'tier': tier
                                    })
                            except Exception as e:
                                continue
                        
                        if players:
                            break
                            
                except Exception as e:
                    print(f"Selector {selector} failed: {e}")
                    continue
            
            if players:
                print(f"Successfully extracted {len(players)} players")
                return players
            else:
                print("No players found with current selectors, trying next URL...")
                
        except Exception as e:
            print(f"Error with URL {url}: {e}")
            continue
    
    # If no URLs worked, try a more generic approach
    if not players:
        print("Trying generic link extraction...")
        try:
            all_links = driver.find_elements(By.TAG_NAME, "a")
            for link in all_links:
                try:
                    href = link.get_attribute('href')
                    text = link.text.strip()
                    
                    if href and text and any(keyword in href for keyword in ['summoner', 'profile', 'player']):
                        if len(text) > 1 and len(text) < 20:  # Reasonable name length
                            players.append({
                                'name': text,
                                'url': href,
                                'region': region,
                                'tier': tier
                            })
                except:
                    continue
            
            print(f"Generic extraction found {len(players)} potential players")
        except Exception as e:
            print(f"Generic extraction failed: {e}")
    
    return players

def get_player_profile_selenium(driver, player_url):
    """
    Scrape detailed player data using Selenium
    """
    try:
        driver.get(player_url)
        human_like_delay()
        
        # Wait for page load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        player_data = {
            'url': player_url,
            'scraped_at': time.time(),
            'page_title': driver.title,
            'success': True
        }
        
        # Try to extract rank information
        rank_selectors = [
            ".tier",
            ".rank",
            ".league-tier",
            "[class*='tier']",
            "[class*='rank']"
        ]
        
        for selector in rank_selectors:
            try:
                rank_element = driver.find_element(By.CSS_SELECTOR, selector)
                player_data['rank'] = rank_element.text.strip()
                break
            except:
                continue
        
        # Try to extract match history
        try:
            matches = driver.find_elements(By.CSS_SELECTOR, "[class*='match'], [class*='game']")
            player_data['match_count'] = len(matches)
        except:
            player_data['match_count'] = 0
        
        # Get page source for later analysis
        player_data['page_source_length'] = len(driver.page_source)
        
        return player_data
        
    except Exception as e:
        print(f"Error scraping profile {player_url}: {e}")
        return {
            'url': player_url,
            'scraped_at': time.time(),
            'success': False,
            'error': str(e)
        }

def test_selenium_connection():
    """Test if Selenium can access OP.GG"""
    driver = setup_driver(headless=True)
    if not driver:
        return False
    
    try:
        driver.get("https://www.op.gg")
        time.sleep(3)
        
        if "403" in driver.title or "Forbidden" in driver.page_source:
            print("✗ OP.GG is blocking access")
            return False
        else:
            print(f"✓ Successfully loaded OP.GG: {driver.title}")
            return True
            
    except Exception as e:
        print(f"✗ Selenium test failed: {e}")
        return False
    finally:
        driver.quit()

def main_selenium():
    """Main function using Selenium"""
    print("Testing Selenium connection to OP.GG...")
    
    if not test_selenium_connection():
        print("Cannot access OP.GG with Selenium. Try:")
        print("1. Using a VPN")
        print("2. Trying again later")
        print("3. Using the original Riot API approach")
        return
    
    # Setup driver for main scraping
    driver = setup_driver(headless=False)  # Set to True to hide browser
    if not driver:
        return
    
    all_players = []
    
    try:
        # Collect players from different tiers
        tiers = ["challenger", "grandmaster", "master"]
        
        for tier in tiers:
            print(f"\nCollecting {tier} players...")
            
            try:
                players = get_leaderboard_players_selenium(driver, "na", tier)
                all_players.extend(players)
                print(f"Found {len(players)} {tier} players")
                
                # Human-like delay between tiers
                time.sleep(random.uniform(10, 20))
                
            except Exception as e:
                print(f"Error collecting {tier} players: {e}")
                continue
        
        # Remove duplicates
        unique_players = {player['url']: player for player in all_players}.values()
        all_players = list(unique_players)
        
        print(f"\nTotal unique players found: {len(all_players)}")
        
        # Save results
        with open("opgg_selenium_players.json", "w", encoding='utf-8') as f:
            json.dump(all_players, f, indent=2, ensure_ascii=False)
        
        print("Results saved to opgg_selenium_players.json")
        
        # Optionally scrape detailed profiles (comment out if you just want the player list)
        """
        if all_players and len(all_players) > 0:
            print("\\nScraping detailed profiles...")
            detailed_data = {}
            
            for i, player in enumerate(all_players[:10]):  # Limit to first 10 for testing
                print(f"Scraping profile {i+1}/{min(10, len(all_players))}: {player['name']}")
                
                profile_data = get_player_profile_selenium(driver, player['url'])
                detailed_data[player['url']] = profile_data
                
                # Human-like delay
                time.sleep(random.uniform(5, 10))
            
            # Save detailed data
            with open("opgg_detailed_profiles.json", "w", encoding='utf-8') as f:
                json.dump(detailed_data, f, indent=2, ensure_ascii=False)
            
            print("Detailed profiles saved to opgg_detailed_profiles.json")
        """
        
    finally:
        driver.quit()

if __name__ == "__main__":
    # Check if selenium is installed
    try:
        import selenium
        print("Selenium is installed")
    except ImportError:
        print("Installing selenium...")
        os.system("pip install selenium")
        import selenium
    
    main_selenium()
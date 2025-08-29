"""
Options Scraper Module
Refactored from testing_options_scraper_auto.ipynb for Airflow compatibility
"""
import os
import sys
import json
import time
import random
import hashlib
import argparse
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.common.action_chains import ActionChains
import re
import coolname

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(current_dir)
sys.path.append(os.path.join(parent_dir, 'config'))
sys.path.append(os.path.join(parent_dir, 'database'))

from database_utils import connect_to_database, close_database_connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OptionsScraperConfig:
    """Configuration class for the options scraper"""
    def __init__(self, config_path: str = '../config/credentials.json'):
        self.config_path = config_path
        self.strategies = [
            {
                "url": "https://optionrecom.com/bear-call-spread-strategy/",
                "type": "Bear Call"
            },
            {
                "url": "https://optionrecom.com/bull-put-spread-strategy/",
                "type": "Bull Put"
            }
        ]

def load_web_credentials(config_path: str = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Load username and password from credentials.json file
    
    Args:
        config_path: Path to credentials.json file
    
    Returns:
        tuple: (username, password) or (None, None) if credentials not found
    """
    if config_path is None:
        # Try to find the credentials file
        possible_paths = [
            '../config/credentials.json',
            '../../config/credentials.json',
            '/home/chris_s_dodd/optcom-1/config/credentials.json'
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                config_path = path
                break
        
        if config_path is None:
            logger.error("Could not find credentials.json file")
            return None, None
    
    try:
        if not os.path.exists(config_path):
            logger.error(f"Credentials file '{config_path}' not found")
            return None, None
        
        with open(config_path, 'r') as f:
            creds = json.load(f)
        
        web_creds = creds.get('web_scraping', {}).get('optionrecom', {})
        username = web_creds.get('username')
        password = web_creds.get('password')
        
        if not username or not password:
            logger.error("Web scraping credentials not found in credentials.json")
            return None, None
        
        if username == "your_username_or_email" or password == "your_password":
            logger.error("Please update the web scraping credentials in config/credentials.json")
            return None, None
        
        logger.info("✅ Web scraping credentials loaded from config/credentials.json")
        return username, password
        
    except Exception as e:
        logger.error(f"Error reading credentials from JSON file: {e}")
        return None, None

def setup_chrome_driver(headless: bool = True) -> Optional[webdriver.Chrome]:
    """
    Set up Chrome WebDriver with robust configuration
    
    Args:
        headless: Whether to run in headless mode
        
    Returns:
        WebDriver instance or None on failure
    """
    # Cleanup existing Chrome processes
    try:
        logger.info("🧹 Cleaning up existing Chrome processes...")
        os.system("pkill -9 -f chrome 2>/dev/null || true")
        os.system("pkill -9 -f chromium 2>/dev/null || true")
        os.system("rm -rf /tmp/.org.chromium.* 2>/dev/null || true")
        os.system("rm -rf /tmp/chrome_* 2>/dev/null || true")
        time.sleep(3)
    except:
        pass
    
    chrome_options = ChromeOptions()
    
    if headless:
        chrome_options.add_argument('--headless=new')
    
    # Essential arguments
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-plugins')
    chrome_options.add_argument('--disable-images')
    chrome_options.add_argument('--no-first-run')
    chrome_options.add_argument('--disable-default-apps')
    chrome_options.add_argument('--disable-sync')
    chrome_options.add_argument('--disable-background-networking')
    chrome_options.add_argument('--window-size=1920,1080')
    
    # Random debug port
    debug_port = random.randint(20000, 60000)
    chrome_options.add_argument(f'--remote-debugging-port={debug_port}')
    
    # Disable automation detection
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            logger.info(f"🚀 Attempting to start Chrome ({'headless' if headless else 'visible'}) (attempt {attempt + 1}/{max_attempts})...")
            
            driver = webdriver.Chrome(
                service=ChromeService(ChromeDriverManager().install()), 
                options=chrome_options
            )
            
            driver.get("about:blank")
            logger.info("✅ Chrome started successfully!")
            return driver
            
        except Exception as e:
            logger.error(f"❌ Attempt {attempt + 1} failed: {e}")
            
            if attempt < max_attempts - 1:
                os.system("pkill -9 -f chrome 2>/dev/null || true")
                time.sleep(2)
                debug_port = random.randint(20000, 60000)
                chrome_options.add_argument(f'--remote-debugging-port={debug_port}')
    
    logger.error("❌ Failed to start Chrome driver")
    return None

def automated_login(driver: webdriver.Chrome, username: str, password: str, max_retries: int = 3) -> bool:
    """
    Perform automated login to optionrecom.com
    
    Args:
        driver: Selenium WebDriver instance
        username: Username or email
        password: Password
        max_retries: Maximum number of login attempts
    
    Returns:
        bool: True if login successful, False otherwise
    """
    for attempt in range(max_retries):
        try:
            logger.info(f"Login attempt {attempt + 1} of {max_retries}...")
            
            driver.get("https://optionrecom.com/my-account-2/")
            time.sleep(3)
            
            # Find and fill username
            username_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            username_field.clear()
            username_field.send_keys(username)
            logger.info("Username entered successfully")
            
            # Find and fill password
            password_field = driver.find_element(By.NAME, "password")
            password_field.clear()
            password_field.send_keys(password)
            logger.info("Password entered successfully")
            
            # Find and click login button
            login_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@name='login']"))
            )
            
            driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", login_button)
            time.sleep(1)
            
            # Try multiple click methods
            click_successful = False
            
            try:
                WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//button[@name='login']")))
                login_button.click()
                click_successful = True
                logger.info("Login button clicked (normal click)")
            except ElementClickInterceptedException:
                logger.info("Normal click intercepted, trying alternative methods...")
            
            if not click_successful:
                try:
                    actions = ActionChains(driver)
                    actions.move_to_element(login_button).click().perform()
                    click_successful = True
                    logger.info("Login button clicked (ActionChains)")
                except Exception as e:
                    logger.error(f"ActionChains click failed: {e}")
            
            if not click_successful:
                try:
                    driver.execute_script("arguments[0].click();", login_button)
                    click_successful = True
                    logger.info("Login button clicked (JavaScript)")
                except Exception as e:
                    logger.error(f"JavaScript click failed: {e}")
            
            if not click_successful:
                raise Exception("All click methods failed")
            
            time.sleep(5)
            
            current_url = driver.current_url
            if "my-account" in current_url and "login" not in current_url.lower():
                logger.info("Login successful!")
                return True
                
        except Exception as e:
            logger.error(f"Login attempt {attempt + 1} failed: {e}")
            
        if attempt < max_retries - 1:
            logger.info("Retrying in 3 seconds...")
            time.sleep(3)
    
    logger.error(f"Login failed after {max_retries} attempts")
    return False

def generate_trade_id(scrape_date: str, strategy_type: str, tab_name: str, ticker: str, trigger_price: str, strike_price: str) -> str:
    """
    Generate a human-readable 3-word trade_id using coolname library
    
    Args:
        scrape_date: Date when data was scraped
        strategy_type: Type of strategy
        tab_name: Risk level and expiry category
        ticker: Stock ticker symbol
        trigger_price: Price that triggers the strategy
        strike_price: Strike prices for the option spread
    
    Returns:
        str: Human-readable trade ID
    """
    components = [
        str(scrape_date) if scrape_date is not None else '',
        str(strategy_type) if strategy_type is not None else '',
        str(tab_name) if tab_name is not None else '',
        str(ticker) if ticker is not None else '',
        str(trigger_price) if trigger_price is not None else '',
        str(strike_price) if strike_price is not None else ''
    ]
    
    combined_string = '|'.join(components)
    hash_value = hashlib.sha256(combined_string.encode('utf-8')).hexdigest()
    hash_seed = int(hash_value[:8], 16)
    
    random.seed(hash_seed)
    trade_id = '-'.join(coolname.generate(3))
    
    return trade_id

def extract_table_data_from_strategy(driver: webdriver.Chrome, strategy_url: str, strategy_type: str, cursor) -> int:
    """
    Extract data from a strategy page and save to database
    
    Args:
        driver: Selenium WebDriver instance
        strategy_url: URL of the strategy page
        strategy_type: Type of strategy (Bear Call, Bull Put, etc.)
        cursor: Database cursor
        
    Returns:
        int: Number of records extracted
    """
    try:
        logger.info(f"Processing {strategy_type} Strategy Page: {strategy_url}")
        driver.get(strategy_url)
        time.sleep(5)
        
        # Extract date from page
        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text
            date_pattern = r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+\w*,\s+\d{4}'
            matches = re.findall(date_pattern, page_text)
            date_info = matches[0] if matches else "Date not found"
        except:
            date_info = "Date extraction error"
        
        # Note: Options expiry date will be extracted per tab instead of globally
        
        # Find tabs
        tabs = []
        tab_selectors = [
            "//div[contains(@class, 'ep_tabs_header')]//a[contains(@class, 'ep_label_main')]",
            "//a[contains(@class, 'ep_label_main')]",
            "//div[contains(@class, 'tabs')]//a",
        ]
        
        for selector in tab_selectors:
            try:
                found_tabs = driver.find_elements(By.XPATH, selector)
                if found_tabs:
                    tabs = found_tabs
                    logger.info(f"Found {len(tabs)} tabs using selector: {selector}")
                    break
            except:
                continue
        
        if not tabs:
            logger.warning(f"No tabs found for {strategy_type}")
            return 0
        
        total_records = 0
        num_tabs_to_process = min(4, len(tabs))
        
        for i, tab in enumerate(tabs[:num_tabs_to_process]):
            try:
                tab_name = tab.text.strip().replace('\n', ' ')
                logger.info(f"Processing Tab {i+1}: '{tab_name}'")
                
                # Click tab
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab)
                time.sleep(1)
                
                try:
                    tab.click()
                except:
                    driver.execute_script("arguments[0].click();", tab)
                
                time.sleep(3)
                
                # Extract options expiry date for this specific tab
                try:
                    # Try to get text from the active tab panel/content area
                    tab_options_expiry_date = None
                    
                    # Method 1: Look for active tab panel content
                    try:
                        tab_panels = driver.find_elements(By.XPATH, "//div[contains(@class, 'ep_tabs_content')]//div[contains(@style, 'display: block') or not(contains(@style, 'display: none'))]")
                        if not tab_panels:
                            # Try alternative selectors for tab content
                            tab_panels = driver.find_elements(By.XPATH, "//div[contains(@class, 'tab-content')]//div[contains(@class, 'active') or contains(@class, 'show')]")
                        
                        if tab_panels:
                            tab_content = tab_panels[0].text
                            logger.debug(f"Found tab panel content for '{tab_name}': {len(tab_content)} characters")
                        else:
                            # Fallback to body text
                            tab_content = driver.find_element(By.TAG_NAME, "body").text
                            logger.debug(f"Using body text for '{tab_name}': {len(tab_content)} characters")
                    except:
                        # Final fallback
                        tab_content = driver.find_element(By.TAG_NAME, "body").text
                    
                    # Method 2: Look for expiry date patterns
                    expiry_patterns = [
                        r'Options\s+Expiry\s+Date:\s*(\d{4}-\d{2}-\d{2})',  # Primary pattern
                        r'Expiry\s*[:\-]\s*(\d{4}-\d{2}-\d{2})',           # Alternative pattern
                        r'(\d{4}-\d{2}-\d{2})',                           # Any YYYY-MM-DD format
                        r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',            # MM/DD/YYYY or DD/MM/YYYY
                    ]
                    
                    for pattern in expiry_patterns:
                        matches = re.findall(pattern, tab_content, re.IGNORECASE)
                        if matches:
                            # If multiple matches, try to pick the most relevant one
                            if len(matches) > 1:
                                # Look for dates that are reasonable (within next 2 years)
                                today = datetime.now()
                                future_limit = today + timedelta(days=730)  # 2 years from now
                                
                                valid_dates = []
                                for match in matches:
                                    try:
                                        if '-' in match and len(match.split('-')) == 3:
                                            # YYYY-MM-DD format
                                            date_obj = datetime.strptime(match, '%Y-%m-%d')
                                            if today <= date_obj <= future_limit:
                                                valid_dates.append((match, date_obj))
                                    except:
                                        continue
                                
                                if valid_dates:
                                    # Sort by date and pick the closest reasonable one
                                    valid_dates.sort(key=lambda x: x[1])
                                    tab_options_expiry_date = valid_dates[0][0]
                                    logger.info(f"Found options expiry date for tab '{tab_name}': {tab_options_expiry_date} (from {len(matches)} candidates)")
                                    break
                            else:
                                tab_options_expiry_date = matches[0]
                                logger.info(f"Found options expiry date for tab '{tab_name}': {tab_options_expiry_date}")
                                break
                    
                    # Method 3: Intelligent fallback based on tab name
                    if not tab_options_expiry_date:
                        today = datetime.now()
                        
                        if "shorter" in tab_name.lower() or "short" in tab_name.lower():
                            # Shorter expiry: ~2-4 weeks out
                            expiry_date = today + timedelta(days=21)
                            tab_options_expiry_date = expiry_date.strftime('%Y-%m-%d')
                            logger.warning(f"No expiry found for shorter expiry tab '{tab_name}', using calculated: {tab_options_expiry_date}")
                        elif "longer" in tab_name.lower() or "long" in tab_name.lower():
                            # Longer expiry: ~6-12 weeks out  
                            expiry_date = today + timedelta(days=70)
                            tab_options_expiry_date = expiry_date.strftime('%Y-%m-%d')
                            logger.warning(f"No expiry found for longer expiry tab '{tab_name}', using calculated: {tab_options_expiry_date}")
                        else:
                            # Default: ~6 weeks out
                            expiry_date = today + timedelta(days=42)
                            tab_options_expiry_date = expiry_date.strftime('%Y-%m-%d')
                            logger.warning(f"No expiry found for tab '{tab_name}', using calculated default: {tab_options_expiry_date}")
                            
                except Exception as e:
                    logger.error(f"Error extracting expiry date for tab '{tab_name}': {e}")
                    # Emergency fallback
                    today = datetime.now()
                    if "shorter" in tab_name.lower():
                        expiry_date = today + timedelta(days=21)
                    elif "longer" in tab_name.lower():
                        expiry_date = today + timedelta(days=70)
                    else:
                        expiry_date = today + timedelta(days=42)
                    tab_options_expiry_date = expiry_date.strftime('%Y-%m-%d')
                    logger.warning(f"Using emergency fallback expiry for tab '{tab_name}': {tab_options_expiry_date}")
                
                # Find table
                tables = driver.find_elements(By.TAG_NAME, "table")
                visible_tables = [t for t in tables if t.is_displayed()]
                
                if not visible_tables:
                    logger.warning(f"No visible tables in tab {i+1}")
                    continue
                
                table = visible_tables[0]  # Use first visible table
                
                # Extract headers and data
                headers = table.find_elements(By.TAG_NAME, "th")
                header_texts = [header.text.strip() for header in headers]
                
                # Find column indices
                column_map = {'ID': -1, 'Ticker': -1, 'Trigger Price': -1, 'Strike Price': -1, 'Estimated Premium': -1}
                
                for idx, header in enumerate(header_texts):
                    h_upper = header.upper()
                    if 'ID' in h_upper and column_map['ID'] == -1:
                        column_map['ID'] = idx
                    elif ('TICKER' in h_upper or 'SYMBOL' in h_upper) and column_map['Ticker'] == -1:
                        column_map['Ticker'] = idx
                    elif ('TRIGGER' in h_upper and 'PRICE' in h_upper) and column_map['Trigger Price'] == -1:
                        column_map['Trigger Price'] = idx
                    elif 'STRIKE' in h_upper and 'PRICE' in h_upper and column_map['Strike Price'] == -1:
                        column_map['Strike Price'] = idx
                    elif 'PREMIUM' in h_upper and column_map['Estimated Premium'] == -1:
                        column_map['Estimated Premium'] = idx
                
                # Extract rows
                rows = table.find_elements(By.TAG_NAME, "tr")[1:]  # Skip header
                records_count = 0
                
                for row_idx, row in enumerate(rows):
                    try:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        if not cells:
                            continue
                        
                        # Extract data from cells
                        item_id = cells[column_map['ID']].text.strip() if column_map['ID'] != -1 and column_map['ID'] < len(cells) else f"AUTO_{row_idx+1}"
                        ticker_raw = cells[column_map['Ticker']].text.strip() if column_map['Ticker'] != -1 and column_map['Ticker'] < len(cells) else 'N/A'
                        
                        # Check for (ER) in ticker
                        er_value = 0
                        if "(ER)" in ticker_raw:
                            ticker = ticker_raw.replace("(ER)", "").strip()
                            er_value = 1
                        else:
                            ticker = ticker_raw
                        
                        # Skip invalid tickers
                        if not ticker or ticker.lower() in ['n/a', 'none', '', 'null']:
                            logger.warning(f"Skipping row {row_idx + 1} - invalid ticker: '{ticker}'")
                            continue
                        
                        trigger_price = cells[column_map['Trigger Price']].text.strip() if column_map['Trigger Price'] != -1 and column_map['Trigger Price'] < len(cells) else 'N/A'
                        strike_price = cells[column_map['Strike Price']].text.strip() if column_map['Strike Price'] != -1 and column_map['Strike Price'] < len(cells) else 'N/A'
                        estimated_premium = cells[column_map['Estimated Premium']].text.strip() if column_map['Estimated Premium'] != -1 and column_map['Estimated Premium'] < len(cells) else 'N/A'
                        
                        # Parse strike prices
                        strike_buy_value, strike_sell_value = 0.0, 0.0
                        if " - " in strike_price:
                            parts = strike_price.split(" - ")
                            if len(parts) == 2:
                                try:
                                    sell_match = re.search(r'(\d+\.?\d*)', parts[0].strip())
                                    buy_match = re.search(r'(\d+\.?\d*)', parts[1].strip())
                                    
                                    if sell_match:
                                        strike_sell_value = float(sell_match.group(1))
                                    if buy_match:
                                        strike_buy_value = float(buy_match.group(1))
                                except ValueError as e:
                                    logger.error(f"Error parsing strike prices: {e}")
                        
                        # Generate trade ID
                        scrape_date_iso = datetime.now().isoformat()
                        trade_id = generate_trade_id(scrape_date_iso, strategy_type, tab_name, ticker, trigger_price, strike_price)
                        
                        # Insert into database
                        cursor.execute('''
                        INSERT INTO option_strategies (
                            scrape_date, strategy_type, tab_name, ticker, trigger_price, 
                            strike_price, strike_buy, strike_sell, estimated_premium, item_id, 
                            options_expiry_date, date_info, er, trade_id
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ''', (
                            scrape_date_iso, strategy_type, tab_name, ticker, trigger_price, 
                            strike_price, strike_buy_value, strike_sell_value, estimated_premium, item_id, 
                            tab_options_expiry_date, date_info, er_value, trade_id
                        ))
                        
                        records_count += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing row {row_idx + 1}: {e}")
                        continue
                
                logger.info(f"Successfully saved {records_count} records from tab {i+1}")
                total_records += records_count
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Error processing tab {i+1}: {e}")
                continue
        
        return total_records
        
    except Exception as e:
        logger.error(f"Error processing {strategy_type} strategy page: {e}")
        return 0

def run_options_scraper(test_mode: bool = False, headless: bool = True) -> int:
    """
    Main function to run the options scraper
    Airflow-compatible version
    
    Args:
        test_mode: If True, runs in test mode with limited data
        headless: Whether to run Chrome in headless mode
        
    Returns:
        int: Number of records scraped
    """
    logger.info("🚀 Starting Options Scraper")
    
    # Load credentials
    username, password = load_web_credentials()
    if not username or not password:
        logger.error("Failed to load web scraping credentials")
        return 0
    
    # Connect to database
    conn, cursor = connect_to_database()
    if not conn or not cursor:
        logger.error("Failed to connect to database")
        return 0
    
    driver = None
    try:
        # Setup Chrome driver
        driver = setup_chrome_driver(headless=headless)
        if not driver:
            logger.error("Failed to setup Chrome driver")
            return 0
        
        # Perform login
        if not automated_login(driver, username, password):
            logger.error("Login failed")
            return 0
        
        # Load configuration
        config = OptionsScraperConfig()
        total_records = 0
        
        # Process each strategy
        for strategy in config.strategies:
            records = extract_table_data_from_strategy(
                driver, strategy["url"], strategy["type"], cursor
            )
            total_records += records
            conn.commit()  # Commit after each strategy
            time.sleep(3)
        
        logger.info(f"🎯 Total records scraped: {total_records}")
        return total_records
        
    except Exception as e:
        logger.error(f"Error in options scraper: {e}")
        return 0
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        close_database_connection(conn, cursor)

def main():
    """Standalone execution entry point"""
    parser = argparse.ArgumentParser(description='Options Scraper')
    parser.add_argument('--test-mode', action='store_true', help='Run in test mode')
    parser.add_argument('--headless', action='store_true', default=True, help='Run Chrome in headless mode')
    parser.add_argument('--visible', action='store_true', help='Run Chrome in visible mode')
    
    args = parser.parse_args()
    
    headless = args.headless and not args.visible
    
    if args.test_mode:
        logger.info("Running in test mode...")
    
    result = run_options_scraper(test_mode=args.test_mode, headless=headless)
    logger.info(f"Scraper completed: {result} records processed")
    return result

if __name__ == "__main__":
    main()
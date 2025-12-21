"""
Trade Perspectives Scraper Module
Scrapes closed and open trade perspectives from optionrecom.com
Converted from scrape_trade_perspectives.ipynb for Airflow integration
"""
import os
import sys
import json
import time
import random
import logging
from datetime import datetime
from typing import Optional, Tuple, List

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

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(os.path.join(parent_dir, 'config'))
sys.path.append(os.path.join(parent_dir, 'database'))

from database_config import DatabaseConnection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_web_credentials(config_path: str = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Load username and password from credentials.json file
    """
    if config_path is None:
        config_path = '/home/chris_s_dodd/optcom-1/config/credentials.json'

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

        logger.info("✅ Web scraping credentials loaded")
        return username, password

    except Exception as e:
        logger.error(f"Error reading credentials: {e}")
        return None, None


def setup_chrome_driver(headless: bool = True) -> Optional[webdriver.Chrome]:
    """
    Set up Chrome WebDriver with robust configuration
    Matches the pattern from options_scraper.py
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

    # Essential arguments (matching options_scraper.py exactly)
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
    """
    for attempt in range(max_retries):
        try:
            logger.info(f"🔑 Login attempt {attempt + 1} of {max_retries}...")

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
                logger.info("✅ Login successful!")
                return True

        except Exception as e:
            logger.error(f"❌ Login attempt {attempt + 1} failed: {e}")

        if attempt < max_retries - 1:
            logger.info("Retrying in 3 seconds...")
            time.sleep(3)

    logger.error(f"❌ Login failed after {max_retries} attempts")
    return False


def extract_perspectives_data(driver: webdriver.Chrome, strategy_url: str, strategy_type: str) -> Tuple[List, List]:
    """
    Extract closed and open trade perspectives from a strategy page
    Returns: (closed_records, open_records)
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing {strategy_type} Strategy Page")
    logger.info(f"{'='*60}")

    driver.get(strategy_url)
    time.sleep(5)

    # Scroll down to find the perspectives section
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(2)
    except:
        pass

    # Find tabs for perspectives
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
                logger.info(f"✅ Found {len(tabs)} tabs")
                break
        except:
            continue

    if not tabs:
        logger.warning(f"❌ No tabs found for {strategy_type}")
        return [], []

    all_closed_records = []
    all_open_records = []

    # The page has 8 tabs total:
    # Tabs 0-3: Trade Ideas tabs
    # Tabs 4-7: In-Progress and Settled Trade Perspectives tabs
    # We only want to process tabs 4-7 (indices 4,5,6,7)

    if len(tabs) < 8:
        logger.warning(f"⚠️  Expected 8 tabs but found {len(tabs)}")
        logger.warning(f"   Tab names: {[t.text.strip().replace('\\n', ' ') for t in tabs]}")

    # Process only tabs 4-7 (perspectives tabs)
    perspectives_tabs = tabs[4:8] if len(tabs) >= 8 else []

    if not perspectives_tabs:
        logger.error(f"❌ Could not find perspectives tabs (tabs 4-7)")
        return [], []

    logger.info(f"✅ Processing {len(perspectives_tabs)} perspectives tabs (indices 4-7)")

    # Track unique tickers per tab to detect content changes
    previous_tickers = set()

    for i, tab in enumerate(perspectives_tabs):
        try:
            tab_name = tab.text.strip().replace('\n', ' ')
            logger.info(f"\n📋 Processing Tab {i+1}: '{tab_name}'")

            # Click tab
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab)
            time.sleep(1)

            try:
                tab.click()
            except:
                driver.execute_script("arguments[0].click();", tab)

            time.sleep(3)

            # Find all tables on the page
            tables = driver.find_elements(By.TAG_NAME, "table")
            visible_tables = [t for t in tables if t.is_displayed()]

            logger.info(f"   Found {len(visible_tables)} visible tables")

            # Track tickers from this tab to detect if content changed
            current_tickers = set()

            # Try to identify which tables are perspectives tables
            for table_idx, table in enumerate(visible_tables):
                try:
                    # Get table headers
                    headers = table.find_elements(By.TAG_NAME, "th")
                    header_texts = [h.text.strip() for h in headers]

                    # Skip if this looks like the main trade ideas table
                    if 'Trigger Price' in header_texts or 'Estimated Premium' in header_texts:
                        logger.debug(f"   Skipping table {table_idx+1} (trade ideas table)")
                        continue

                    # Check if this is a perspectives table
                    has_entered_date = any('Entered' in h for h in header_texts)
                    has_expiry_date = any('Expiry' in h for h in header_texts)
                    has_strike_prices = any('Strike' in h for h in header_texts)
                    has_status = any('Status' in h for h in header_texts)
                    has_premium_collected = any('Premium' in h for h in header_texts)

                    if not (has_entered_date and has_expiry_date and has_strike_prices and has_status):
                        continue

                    # Determine if this is closed or open perspectives
                    is_open = has_premium_collected
                    table_type = "Open" if is_open else "Closed"

                    logger.info(f"   ✅ Found {table_type} Perspectives table (table {table_idx+1})")

                    # Find column indices
                    column_map = {}
                    for idx, header in enumerate(header_texts):
                        h_upper = header.upper()
                        if 'TICKER' in h_upper or 'SYMBOL' in h_upper:
                            column_map['Ticker'] = idx
                        elif 'ENTERED' in h_upper and 'DATE' in h_upper:
                            column_map['Entered Date'] = idx
                        elif 'EXPIRY' in h_upper and 'DATE' in h_upper:
                            column_map['Expiry Date'] = idx
                        elif 'STRIKE' in h_upper and 'PRICE' in h_upper:
                            column_map['Strike Prices'] = idx
                        elif 'STATUS' in h_upper:
                            column_map['Status'] = idx
                        elif 'PREMIUM' in h_upper and 'COLLECTED' in h_upper:
                            column_map['Premium Collected'] = idx

                    # Extract rows
                    rows = table.find_elements(By.TAG_NAME, "tr")
                    data_rows = rows[1:]  # Skip header

                    records_count = 0
                    scrape_date = datetime.now()

                    for row in data_rows:
                        try:
                            cells = row.find_elements(By.TAG_NAME, "td")
                            if not cells or len(cells) < 4:
                                continue

                            ticker = cells[column_map['Ticker']].text.strip() if 'Ticker' in column_map else 'N/A'
                            entered_date = cells[column_map['Entered Date']].text.strip() if 'Entered Date' in column_map else 'N/A'
                            expiry_date = cells[column_map['Expiry Date']].text.strip() if 'Expiry Date' in column_map else 'N/A'
                            strike_prices = cells[column_map['Strike Prices']].text.strip() if 'Strike Prices' in column_map else 'N/A'
                            status = cells[column_map['Status']].text.strip() if 'Status' in column_map else 'N/A'

                            # Skip invalid rows
                            if not ticker or ticker.lower() in ['n/a', 'none', '', 'null']:
                                continue

                            # Track ticker for content change detection
                            current_tickers.add(ticker)

                            record = {
                                'scrape_date': scrape_date,
                                'strategy_type': strategy_type,
                                'tab_name': tab_name,
                                'ticker': ticker,
                                'entered_date': entered_date,
                                'expiry_date': expiry_date,
                                'strike_prices': strike_prices,
                                'status': status
                            }

                            if is_open:
                                premium_collected = cells[column_map['Premium Collected']].text.strip() if 'Premium Collected' in column_map else 'N/A'
                                record['premium_collected'] = premium_collected
                                all_open_records.append(record)
                            else:
                                all_closed_records.append(record)

                            records_count += 1

                        except Exception as e:
                            logger.warning(f"      ⚠️  Error processing row: {e}")
                            continue

                    logger.info(f"      📊 Extracted {records_count} records from {table_type} Perspectives table")

                except Exception as e:
                    logger.warning(f"   ⚠️  Error processing table {table_idx+1}: {e}")
                    continue

            # Warn if content appears to be duplicated from previous tab
            if current_tickers and previous_tickers and current_tickers == previous_tickers:
                logger.warning(f"   ⚠️  WARNING: Tab content appears identical to previous tab!")
                logger.warning(f"      Current tab tickers: {sorted(current_tickers)}")
                logger.warning(f"      This suggests tab switching may not be working correctly")

            previous_tickers = current_tickers
            time.sleep(2)

        except Exception as e:
            logger.error(f"❌ Error processing tab {i+1}: {e}")
            continue

    logger.info(f"\n✅ Total records extracted:")
    logger.info(f"   Closed Perspectives: {len(all_closed_records)}")
    logger.info(f"   Open Perspectives: {len(all_open_records)}")

    return all_closed_records, all_open_records


def insert_closed_perspectives(records: List[dict], db_connection: DatabaseConnection) -> int:
    """
    Insert closed trade perspectives into PostgreSQL
    Uses ON CONFLICT DO UPDATE to update scrape_date for existing perspectives
    """
    if not records:
        logger.info("No closed perspective records to insert")
        return 0

    insert_query = '''
    INSERT INTO closed_trade_perspectives (
        scrape_date, strategy_type, tab_name, ticker, entered_date,
        expiry_date, strike_prices, status
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (strategy_type, tab_name, ticker, entered_date, expiry_date, strike_prices, status)
    DO UPDATE SET scrape_date = EXCLUDED.scrape_date
    '''

    params_list = [
        (
            r['scrape_date'], r['strategy_type'], r['tab_name'], r['ticker'],
            r['entered_date'], r['expiry_date'], r['strike_prices'], r['status']
        )
        for r in records
    ]

    # Execute the query
    with db_connection.get_connection() as conn:
        cursor = db_connection.get_cursor(conn)
        cursor.executemany(insert_query, params_list)
        conn.commit()
        rows_affected = cursor.rowcount

    logger.info(f"✅ Processed {len(records)} closed perspective records ({rows_affected} inserted/updated)")
    return len(records)


def insert_open_perspectives(records: List[dict], db_connection: DatabaseConnection) -> int:
    """
    Insert open trade perspectives into PostgreSQL
    Uses ON CONFLICT DO UPDATE to update scrape_date for existing perspectives
    """
    if not records:
        logger.info("No open perspective records to insert")
        return 0

    insert_query = '''
    INSERT INTO open_trade_perspectives (
        scrape_date, strategy_type, tab_name, ticker, entered_date,
        expiry_date, strike_prices, status, premium_collected
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (strategy_type, tab_name, ticker, entered_date, expiry_date, strike_prices, status)
    DO UPDATE SET scrape_date = EXCLUDED.scrape_date, premium_collected = EXCLUDED.premium_collected
    '''

    params_list = [
        (
            r['scrape_date'], r['strategy_type'], r['tab_name'], r['ticker'],
            r['entered_date'], r['expiry_date'], r['strike_prices'], r['status'],
            r['premium_collected']
        )
        for r in records
    ]

    # Execute the query
    with db_connection.get_connection() as conn:
        cursor = db_connection.get_cursor(conn)
        cursor.executemany(insert_query, params_list)
        conn.commit()
        rows_affected = cursor.rowcount

    logger.info(f"✅ Processed {len(records)} open perspective records ({rows_affected} inserted/updated)")
    return len(records)


def run_perspectives_scraper(headless: bool = True) -> Tuple[int, int]:
    """
    Main function to scrape trade perspectives
    Airflow-compatible version

    Args:
        headless: Whether to run Chrome in headless mode

    Returns:
        Tuple[int, int]: (closed_count, open_count)
    """
    logger.info("🚀 Starting Trade Perspectives Scraper")

    # Load credentials
    username, password = load_web_credentials()
    if not username or not password:
        logger.error("Failed to load web scraping credentials")
        return 0, 0

    # Initialize database connection
    db = DatabaseConnection()
    if not db.test_connection():
        logger.error("Failed to connect to database")
        return 0, 0

    driver = None
    try:
        # Setup Chrome driver
        driver = setup_chrome_driver(headless=headless)
        if not driver:
            logger.error("Failed to setup Chrome driver")
            return 0, 0

        # Perform login
        if not automated_login(driver, username, password):
            logger.error("Login failed")
            return 0, 0

        # Define strategies to scrape
        strategies = [
            {
                "url": "https://optionrecom.com/bear-call-spread-strategy/",
                "type": "Bear Call"
            },
            {
                "url": "https://optionrecom.com/bull-put-spread-strategy/",
                "type": "Bull Put"
            }
        ]

        all_closed_records = []
        all_open_records = []

        # Scrape each strategy
        for strategy in strategies:
            closed, opened = extract_perspectives_data(driver, strategy["url"], strategy["type"])
            all_closed_records.extend(closed)
            all_open_records.extend(opened)
            time.sleep(3)

        logger.info(f"\n{'='*60}")
        logger.info(f"SCRAPING COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Total Closed Perspectives: {len(all_closed_records)}")
        logger.info(f"Total Open Perspectives: {len(all_open_records)}")

        # Insert into database
        closed_count = insert_closed_perspectives(all_closed_records, db)
        open_count = insert_open_perspectives(all_open_records, db)

        logger.info(f"\n✅ Database inserts complete")
        logger.info(f"   Closed: {closed_count} records")
        logger.info(f"   Open: {open_count} records")

        return closed_count, open_count

    except Exception as e:
        logger.error(f"Error in perspectives scraper: {e}")
        return 0, 0
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("✅ Browser closed")
            except:
                pass


def main():
    """Standalone execution entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Trade Perspectives Scraper')
    parser.add_argument('--headless', action='store_true', default=True, help='Run Chrome in headless mode')
    parser.add_argument('--visible', action='store_true', help='Run Chrome in visible mode')

    args = parser.parse_args()

    headless = args.headless and not args.visible

    closed_count, open_count = run_perspectives_scraper(headless=headless)
    logger.info(f"\n🎯 Scraper completed:")
    logger.info(f"   Closed perspectives: {closed_count}")
    logger.info(f"   Open perspectives: {open_count}")

    return closed_count + open_count


if __name__ == "__main__":
    main()

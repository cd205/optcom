#!/usr/bin/env python3
"""
Test script to debug tab switching and content extraction
"""
import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# Add config path
sys.path.append('/home/chris_s_dodd/optcom-1/config')

def setup_chrome_driver(headless: bool = False):
    """Quick Chrome setup for testing"""
    chrome_options = ChromeOptions()
    if headless:
        chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')

    driver = webdriver.Chrome(
        service=ChromeService(ChromeDriverManager().install()),
        options=chrome_options
    )
    return driver

def test_tab_content(driver, url: str):
    """Test if tab content actually changes"""
    print(f"\n{'='*80}")
    print(f"Testing Tab Switching on: {url}")
    print(f"{'='*80}\n")

    driver.get(url)
    time.sleep(5)

    # Scroll to perspectives section
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
    time.sleep(2)

    # Find all tabs
    tabs = driver.find_elements(By.XPATH, "//div[contains(@class, 'ep_tabs_header')]//a[contains(@class, 'ep_label_main')]")
    print(f"Found {len(tabs)} tabs total\n")

    # Print all tab names first
    print("All tab names:")
    for i, tab in enumerate(tabs):
        print(f"  Tab {i}: {tab.text.strip().replace(chr(10), ' ')}")
    print()

    # The page has 8 tabs total:
    # Tabs 0-3: Trade Ideas tabs
    # Tabs 4-7: In-Progress and Settled Trade Perspectives tabs
    # We only want to test tabs 4-7

    perspectives_tabs = tabs[4:8] if len(tabs) >= 8 else []

    if not perspectives_tabs:
        print("❌ Could not find perspectives tabs (indices 4-7)")
        return

    print(f"Testing {len(perspectives_tabs)} perspectives tabs (indices 4-7)\n")

    # Test tabs 4-7 (perspectives)
    for i, tab in enumerate(perspectives_tabs):
        tab_name = tab.text.strip().replace('\n', ' ')
        print(f"{'='*80}")
        print(f"TAB {i+1}: {tab_name}")
        print(f"{'='*80}")

        # Click the tab
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", tab)

        # Wait for content to load
        print("Waiting 5 seconds for content to load...")
        time.sleep(5)

        # Method 1: Check for active tab content container
        print("\n[Method 1] Looking for active tab content container...")
        try:
            # Look for div with 'ep_tab_active' class or visible display
            active_containers = driver.find_elements(By.XPATH,
                "//div[contains(@class, 'ep_tab_active') or contains(@class, 'ep_tabs_content_el')]")
            print(f"  Found {len(active_containers)} potential content containers")

            for idx, container in enumerate(active_containers[:3]):  # Check first 3
                if container.is_displayed():
                    # Check if this container has perspective tables
                    container_tables = container.find_elements(By.TAG_NAME, "table")
                    visible_container_tables = [t for t in container_tables if t.is_displayed()]
                    print(f"  Container {idx+1}: {len(visible_container_tables)} visible tables")

                    if visible_container_tables:
                        # Get first row of first perspective table (skip trade ideas table)
                        for table in visible_container_tables:
                            headers = table.find_elements(By.TAG_NAME, "th")
                            header_texts = [h.text.strip() for h in headers]

                            # Skip trade ideas table
                            if 'Trigger Price' in header_texts or 'Estimated Premium' in header_texts:
                                continue

                            # This is a perspectives table
                            rows = table.find_elements(By.TAG_NAME, "tr")
                            if len(rows) > 1:  # Has data rows
                                first_data_row = rows[1]
                                cells = first_data_row.find_elements(By.TAG_NAME, "td")
                                if cells and len(cells) >= 1:
                                    ticker = cells[0].text.strip()
                                    print(f"    → First ticker in this table: {ticker}")
                                break
        except Exception as e:
            print(f"  ⚠️  Error with Method 1: {e}")

        # Method 2: Check all visible tables on page
        print("\n[Method 2] Checking all visible tables on page...")
        all_tables = driver.find_elements(By.TAG_NAME, "table")
        visible_tables = [t for t in all_tables if t.is_displayed()]
        print(f"  Found {len(visible_tables)} visible tables total")

        perspective_table_count = 0
        for table_idx, table in enumerate(visible_tables):
            headers = table.find_elements(By.TAG_NAME, "th")
            header_texts = [h.text.strip() for h in headers]

            # Skip trade ideas table
            if 'Trigger Price' in header_texts or 'Estimated Premium' in header_texts:
                continue

            # Check if perspectives table
            if any('Entered' in h for h in header_texts) and any('Status' in h for h in header_texts):
                perspective_table_count += 1
                has_premium = any('Premium' in h for h in header_texts)
                table_type = "Open" if has_premium else "Closed"

                # Get first 3 tickers from this table
                rows = table.find_elements(By.TAG_NAME, "tr")
                data_rows = rows[1:][:3]  # First 3 data rows
                tickers = []
                for row in data_rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if cells:
                        ticker = cells[0].text.strip()
                        if ticker:
                            tickers.append(ticker)

                print(f"  Table {table_idx+1} ({table_type} Perspectives): {', '.join(tickers)}")

        print(f"\n  Total perspectives tables found: {perspective_table_count}")
        print()

def main():
    print("\n🔍 Tab Switching Debug Test")
    print("This will test if perspective table content changes when tabs are clicked\n")

    # Setup driver in visible mode for debugging
    driver = setup_chrome_driver(headless=False)

    try:
        # Login first
        print("Logging in to optionrecom.com...")
        from credentials_loader import load_credentials
        creds = load_credentials()
        username = creds['web_scraping']['optionrecom']['username']
        password = creds['web_scraping']['optionrecom']['password']

        driver.get("https://optionrecom.com/my-account-2/")
        time.sleep(3)

        username_field = driver.find_element(By.NAME, "username")
        username_field.send_keys(username)

        password_field = driver.find_element(By.NAME, "password")
        password_field.send_keys(password)

        login_button = driver.find_element(By.XPATH, "//button[@name='login']")
        driver.execute_script("arguments[0].click();", login_button)

        time.sleep(5)
        print("✅ Logged in\n")

        # Test Bear Call page
        test_tab_content(driver, "https://optionrecom.com/bear-call-spread-strategy/")

        print("\n" + "="*80)
        print("TEST COMPLETE - Review the output above")
        print("="*80)

        input("\nPress Enter to close browser...")

    finally:
        driver.quit()
        print("Browser closed")

if __name__ == "__main__":
    main()

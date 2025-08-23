import hashlib
import coolname

def generate_coolname_trade_id(scrape_date, strategy_type, tab_name, ticker, trigger_price, strike_price):
    """
    Generate a human-readable trade ID using coolname library
    """
    # Create the same combined string as before
    components = [
        str(scrape_date) if scrape_date is not None else '',
        str(strategy_type) if strategy_type is not None else '',
        str(tab_name) if tab_name is not None else '',
        str(ticker) if ticker is not None else '',
        str(trigger_price) if trigger_price is not None else '',
        str(strike_price) if strike_price is not None else ''
    ]
    combined_string = '|'.join(components)
    
    # Generate hash and use it as seed for reproducible results
    hash_value = hashlib.sha256(combined_string.encode('utf-8')).hexdigest()
    hash_seed = int(hash_value[:8], 16)  # Use first 8 chars as seed
    
    # Generate deterministic coolname
    trade_id = coolname.generate(2, seed=hash_seed)  # 2 words
    
    return trade_id, hash_value

# Test with the same data
test_cases = [
    {
        'scrape_date': '2025-04-11T15:49:43.519952',
        'strategy_type': 'Bear Call',
        'tab_name': 'Mild Risk 95-97% accuracy > shorter expiry',
        'ticker': 'V',
        'trigger_price': '334.75',
        'strike_price': 'sell 350.0 - buy 360.0'
    },
    {
        'scrape_date': '2025-01-15 10:30:00',
        'strategy_type': 'Bull Put Spread', 
        'tab_name': 'Medium Risk - Standard',
        'ticker': 'TSLA',
        'trigger_price': '200.00',
        'strike_price': '195/190'
    },
    {
        'scrape_date': '2025-01-15 10:30:00',
        'strategy_type': 'Bear Call Spread',
        'tab_name': 'High Risk - Near Exp', 
        'ticker': 'AAPL',
        'trigger_price': '150.00',
        'strike_price': '155/160'
    }
]

print("Coolname Trade ID Examples:")
print("=" * 40)

for i, data in enumerate(test_cases, 1):
    coolname_id, full_hash = generate_coolname_trade_id(
        data['scrape_date'],
        data['strategy_type'], 
        data['tab_name'],
        data['ticker'],
        data['trigger_price'],
        data['strike_price']
    )
    
    print(f"Test Case {i}:")
    print(f"  Ticker: {data['ticker']}")
    print(f"  Strategy: {data['strategy_type']}")
    print(f"  Coolname ID: {coolname_id}")
    print(f"  Full Hash: {full_hash[:16]}...")
    print()

# Test consistency
print("Consistency Test:")
print("-" * 25)
data = test_cases[0]
coolname1, _ = generate_coolname_trade_id(
    data['scrape_date'], data['strategy_type'], data['tab_name'],
    data['ticker'], data['trigger_price'], data['strike_price']
)
coolname2, _ = generate_coolname_trade_id(
    data['scrape_date'], data['strategy_type'], data['tab_name'],
    data['ticker'], data['trigger_price'], data['strike_price']
)
print(f"First call:  {coolname1}")
print(f"Second call: {coolname2}")
print(f"Consistent: {coolname1 == coolname2}")
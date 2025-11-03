import hashlib
import random

# Simple word lists for mnemonic generation
ADJECTIVES = [
    'blue', 'red', 'green', 'fast', 'slow', 'big', 'small', 'hot', 'cold', 'bright',
    'dark', 'light', 'heavy', 'soft', 'hard', 'smooth', 'rough', 'clean', 'dirty', 'fresh',
    'old', 'new', 'young', 'wise', 'brave', 'calm', 'bold', 'cool', 'warm', 'sharp'
]

NOUNS = [
    'cat', 'dog', 'bird', 'fish', 'tree', 'rock', 'star', 'moon', 'sun', 'wave',
    'fire', 'wind', 'rain', 'snow', 'leaf', 'seed', 'bear', 'wolf', 'eagle', 'lion',
    'tiger', 'shark', 'whale', 'rose', 'oak', 'pine', 'river', 'mountain', 'valley', 'ocean'
]

VERBS = [
    'runs', 'jumps', 'flies', 'swims', 'dances', 'sings', 'walks', 'climbs', 'rolls', 'spins',
    'glows', 'shines', 'burns', 'flows', 'grows', 'moves', 'plays', 'works', 'builds', 'creates',
    'thinks', 'dreams', 'hopes', 'wins', 'leads', 'helps', 'saves', 'finds', 'makes', 'gives'
]

def generate_mnemonic_trade_id(scrape_date, strategy_type, tab_name, ticker, trigger_price, strike_price):
    """
    Generate a human-readable 3-word mnemonic trade ID
    Uses hash of input data to ensure deterministic results
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
    
    # Generate hash and use it as seed for reproducible "randomness"
    hash_value = hashlib.sha256(combined_string.encode('utf-8')).hexdigest()
    
    # Use parts of hash to select words deterministically
    hash_int = int(hash_value[:16], 16)  # Use first 16 chars of hash as big integer
    
    # Use different parts of the hash for each word selection
    adj_index = (hash_int >> 0) % len(ADJECTIVES)
    noun_index = (hash_int >> 8) % len(NOUNS) 
    verb_index = (hash_int >> 16) % len(VERBS)
    
    mnemonic = f"{ADJECTIVES[adj_index]}-{NOUNS[noun_index]}-{VERBS[verb_index]}"
    
    return mnemonic, hash_value

# Test with sample data
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

print("Mnemonic Trade ID Examples:")
print("=" * 50)

for i, data in enumerate(test_cases, 1):
    mnemonic, full_hash = generate_mnemonic_trade_id(
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
    print(f"  Mnemonic ID: {mnemonic}")
    print(f"  Full Hash: {full_hash[:16]}...")
    print()

# Test consistency - same input should give same mnemonic
print("Consistency Test:")
print("-" * 30)
data = test_cases[0]
mnemonic1, _ = generate_mnemonic_trade_id(
    data['scrape_date'], data['strategy_type'], data['tab_name'],
    data['ticker'], data['trigger_price'], data['strike_price']
)
mnemonic2, _ = generate_mnemonic_trade_id(
    data['scrape_date'], data['strategy_type'], data['tab_name'], 
    data['ticker'], data['trigger_price'], data['strike_price']
)
print(f"First call:  {mnemonic1}")
print(f"Second call: {mnemonic2}")
print(f"Consistent: {mnemonic1 == mnemonic2}")
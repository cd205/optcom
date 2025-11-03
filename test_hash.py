import hashlib

def generate_trade_id(scrape_date, strategy_type, tab_name, ticker, trigger_price, strike_price):
    components = [
        str(scrape_date) if scrape_date is not None else "",
        str(strategy_type) if strategy_type is not None else "",
        str(tab_name) if tab_name is not None else "",
        str(ticker) if ticker is not None else "",
        str(trigger_price) if trigger_price is not None else "",
        str(strike_price) if strike_price is not None else ""
    ]
    combined_string = "|".join(components)
    hash_object = hashlib.sha256(combined_string.encode("utf-8"))
    return hash_object.hexdigest()

print("Testing edge cases and uniqueness:")

test_cases = [
    ("With None values", (None, "Bear Call", "High Risk", "AAPL", "150.00", None)),
    ("Empty strings", ("", "Bear Call", "High Risk", "AAPL", "150.00", "")),
    ("Standard case", ("2025-01-15", "Bear Call", "High Risk", "AAPL", "150.00", "155/160")),
    ("Different strike", ("2025-01-15", "Bear Call", "High Risk", "AAPL", "150.00", "155/161")),
    ("Same as standard", ("2025-01-15", "Bear Call", "High Risk", "AAPL", "150.00", "155/160"))
]

hashes = {}
for name, data in test_cases:
    trade_id = generate_trade_id(*data)
    hashes[name] = trade_id
    print(f"{name}: {trade_id[:16]}...")

hash_values = list(hashes.values())
unique_hashes = set(hash_values)
print(f"\nGenerated {len(hash_values)} hashes, {len(unique_hashes)} unique")
if len(hash_values) != len(unique_hashes):
    print("WARNING: Hash collision detected!")
else:
    print("✓ No hash collisions detected")

standard_hash = hashes["Standard case"]
duplicate_hash = hashes["Same as standard"]
print(f"\nConsistency test:")
print(f"Standard: {standard_hash[:16]}...")
print(f"Duplicate: {duplicate_hash[:16]}...")
print(f"Identical: {standard_hash == duplicate_hash}")
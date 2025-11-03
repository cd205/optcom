-- PostgreSQL Schema for Option Strategies Database
-- Migrated from SQLite option_strategies.db

-- Create the option_strategies table
CREATE TABLE IF NOT EXISTS option_strategies (
    id SERIAL PRIMARY KEY,
    scrape_date TIMESTAMP,
    strategy_type TEXT,
    tab_name TEXT,
    ticker TEXT,
    er INTEGER,
    trigger_price TEXT,
    strike_price TEXT,
    strike_buy REAL,
    strike_sell REAL,
    estimated_premium REAL,
    last_price_when_checked REAL,
    timestamp_of_price_when_last_checked REAL,
    item_id TEXT,
    options_expiry_date TEXT,
    options_expiry_date_as_scrapped TEXT,
    date_info TEXT,
    timestamp_of_trigger TIMESTAMP,
    strategy_status TEXT,
    price_when_triggered REAL,
    price_when_order_placed REAL,
    premium_at_order REAL,
    premium_when_last_checked REAL,
    timestamp_of_order TIMESTAMP,
    trade_id TEXT UNIQUE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_strategy_type ON option_strategies (strategy_type);
CREATE INDEX IF NOT EXISTS idx_ticker ON option_strategies (ticker);
CREATE INDEX IF NOT EXISTS idx_scrape_date ON option_strategies (scrape_date);
CREATE INDEX IF NOT EXISTS idx_strategy_status ON option_strategies (strategy_status);
CREATE INDEX IF NOT EXISTS idx_timestamp_trigger ON option_strategies (timestamp_of_trigger);
CREATE INDEX IF NOT EXISTS idx_trade_id ON option_strategies (trade_id);
CREATE INDEX IF NOT EXISTS idx_options_expiry_date_as_scrapped ON option_strategies (options_expiry_date_as_scrapped);

-- Add comments for documentation
COMMENT ON TABLE option_strategies IS 'Main table storing option trading strategies data';
COMMENT ON COLUMN option_strategies.id IS 'Auto-incrementing primary key';
COMMENT ON COLUMN option_strategies.scrape_date IS 'When the strategy data was scraped';
COMMENT ON COLUMN option_strategies.strategy_type IS 'Type of option strategy (Bear Call, Bull Put, etc.)';
COMMENT ON COLUMN option_strategies.tab_name IS 'Risk level and expiry category';
COMMENT ON COLUMN option_strategies.ticker IS 'Stock ticker symbol';
COMMENT ON COLUMN option_strategies.trigger_price IS 'Price that triggers the strategy';
COMMENT ON COLUMN option_strategies.strike_price IS 'Strike prices for the option spread';
COMMENT ON COLUMN option_strategies.strategy_status IS 'Current status (triggered, etc.)';
COMMENT ON COLUMN option_strategies.timestamp_of_trigger IS 'When the strategy was triggered';
COMMENT ON COLUMN option_strategies.price_when_triggered IS 'Stock price when strategy was triggered';
COMMENT ON COLUMN option_strategies.trade_id IS 'Human-readable unique identifier generated from key trade parameters';
COMMENT ON COLUMN option_strategies.options_expiry_date_as_scrapped IS 'Original expiry date format as scraped from source';
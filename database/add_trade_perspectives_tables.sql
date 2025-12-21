-- PostgreSQL Schema for Trade Perspectives Tables
-- Stores closed and open trade perspectives scraped from optionrecom.com

-- Create the closed_trade_perspectives table
CREATE TABLE IF NOT EXISTS closed_trade_perspectives (
    id SERIAL PRIMARY KEY,
    scrape_date TIMESTAMP,
    strategy_type TEXT,
    tab_name TEXT,
    ticker TEXT,
    entered_date TEXT,
    expiry_date TEXT,
    strike_prices TEXT,
    status TEXT
);

-- Create the open_trade_perspectives table
CREATE TABLE IF NOT EXISTS open_trade_perspectives (
    id SERIAL PRIMARY KEY,
    scrape_date TIMESTAMP,
    strategy_type TEXT,
    tab_name TEXT,
    ticker TEXT,
    entered_date TEXT,
    expiry_date TEXT,
    strike_prices TEXT,
    status TEXT,
    premium_collected TEXT
);

-- Create unique constraints to prevent duplicate entries
-- A perspective is unique by: strategy_type, tab_name, ticker, entered_date, expiry_date, strike_prices, status
CREATE UNIQUE INDEX IF NOT EXISTS idx_closed_unique ON closed_trade_perspectives (
    strategy_type, tab_name, ticker, entered_date, expiry_date, strike_prices, status
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_open_unique ON open_trade_perspectives (
    strategy_type, tab_name, ticker, entered_date, expiry_date, strike_prices, status
);

-- Create indexes for performance on closed_trade_perspectives
CREATE INDEX IF NOT EXISTS idx_closed_ticker ON closed_trade_perspectives (ticker);
CREATE INDEX IF NOT EXISTS idx_closed_expiry_date ON closed_trade_perspectives (expiry_date);
CREATE INDEX IF NOT EXISTS idx_closed_strategy_type ON closed_trade_perspectives (strategy_type);
CREATE INDEX IF NOT EXISTS idx_closed_scrape_date ON closed_trade_perspectives (scrape_date);

-- Create indexes for performance on open_trade_perspectives
CREATE INDEX IF NOT EXISTS idx_open_ticker ON open_trade_perspectives (ticker);
CREATE INDEX IF NOT EXISTS idx_open_expiry_date ON open_trade_perspectives (expiry_date);
CREATE INDEX IF NOT EXISTS idx_open_strategy_type ON open_trade_perspectives (strategy_type);
CREATE INDEX IF NOT EXISTS idx_open_scrape_date ON open_trade_perspectives (scrape_date);

-- Add comments for documentation
COMMENT ON TABLE closed_trade_perspectives IS 'Stores closed/settled trade perspectives from optionrecom.com';
COMMENT ON TABLE open_trade_perspectives IS 'Stores open/in-progress trade perspectives from optionrecom.com';

COMMENT ON COLUMN closed_trade_perspectives.scrape_date IS 'When the perspective data was scraped';
COMMENT ON COLUMN closed_trade_perspectives.strategy_type IS 'Type of strategy (Bear Call, Bull Put, etc.)';
COMMENT ON COLUMN closed_trade_perspectives.tab_name IS 'Risk level and expiry category tab';
COMMENT ON COLUMN closed_trade_perspectives.ticker IS 'Stock ticker symbol';
COMMENT ON COLUMN closed_trade_perspectives.entered_date IS 'Date when the trade was entered';
COMMENT ON COLUMN closed_trade_perspectives.expiry_date IS 'Option expiry date';
COMMENT ON COLUMN closed_trade_perspectives.strike_prices IS 'Strike prices for the spread';
COMMENT ON COLUMN closed_trade_perspectives.status IS 'Trade status/outcome';

COMMENT ON COLUMN open_trade_perspectives.scrape_date IS 'When the perspective data was scraped';
COMMENT ON COLUMN open_trade_perspectives.strategy_type IS 'Type of strategy (Bear Call, Bull Put, etc.)';
COMMENT ON COLUMN open_trade_perspectives.tab_name IS 'Risk level and expiry category tab';
COMMENT ON COLUMN open_trade_perspectives.ticker IS 'Stock ticker symbol';
COMMENT ON COLUMN open_trade_perspectives.entered_date IS 'Date when the trade was entered';
COMMENT ON COLUMN open_trade_perspectives.expiry_date IS 'Option expiry date';
COMMENT ON COLUMN open_trade_perspectives.strike_prices IS 'Strike prices for the spread';
COMMENT ON COLUMN open_trade_perspectives.status IS 'Current trade status';
COMMENT ON COLUMN open_trade_perspectives.premium_collected IS 'Premium collected for the trade';

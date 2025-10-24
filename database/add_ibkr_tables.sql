-- Add IBKR Position Tracking Tables to Existing PostgreSQL Database
-- Run this on your existing database: crafty-water-453519-d7:europe-west4:optcom-postgres

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Main IBKR Positions Table
CREATE TABLE IF NOT EXISTS ibkr_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- IBKR Position Data
    ibkr_symbol VARCHAR(10) NOT NULL,
    ibkr_description TEXT NOT NULL,
    ibkr_avg_cost DECIMAL(10,4),
    ibkr_current_price DECIMAL(10,4),
    ibkr_unrealized_pnl DECIMAL(12,2),
    ibkr_market_val DECIMAL(12,2),
    ibkr_position DECIMAL(10,2),

    -- Database Strategy Reference (links to existing option_strategies table)
    db_id INTEGER,
    db_ticker VARCHAR(10),
    db_strategy_type VARCHAR(50),
    db_trigger_price DECIMAL(10,2),
    db_strike_sell DECIMAL(10,2),
    db_strike_buy DECIMAL(10,2),
    db_estimated_premium DECIMAL(10,2),
    db_options_expiry_date DATE,
    db_scrape_date TIMESTAMP,
    db_strategy_status VARCHAR(50),
    db_trade_id TEXT,

    -- Calculated Fields
    premium_difference DECIMAL(10,4),

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key to existing option_strategies table
    CONSTRAINT fk_option_strategy FOREIGN KEY (db_id) REFERENCES option_strategies(id),

    -- Unique constraint to prevent duplicates
    UNIQUE(ibkr_symbol, ibkr_description, db_id)
);

-- 2. Market Data Snapshots Table (for time-series price data)
CREATE TABLE IF NOT EXISTS market_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    position_id UUID NOT NULL REFERENCES ibkr_positions(id) ON DELETE CASCADE,

    -- Market Data
    current_price DECIMAL(10,4),
    bid_price DECIMAL(10,4),
    ask_price DECIMAL(10,4),
    last_price DECIMAL(10,4),
    volume INTEGER,

    -- Data Source Information
    data_source VARCHAR(50) DEFAULT 'IBKR', -- 'IBKR', 'Yahoo', 'Manual', etc.
    data_quality VARCHAR(20) DEFAULT 'real-time', -- 'real-time', 'delayed', 'snapshot'

    -- Timestamp
    snapshot_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_position_market FOREIGN KEY (position_id) REFERENCES ibkr_positions(id)
);

-- 3. Options Greeks Table (for options-specific data)
CREATE TABLE IF NOT EXISTS options_greeks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    position_id UUID NOT NULL REFERENCES ibkr_positions(id) ON DELETE CASCADE,

    -- The Greeks
    delta DECIMAL(8,6),
    gamma DECIMAL(8,6),
    theta DECIMAL(8,6),
    vega DECIMAL(8,6),
    rho DECIMAL(8,6),

    -- Volatility and Values
    implied_volatility DECIMAL(8,6),
    time_value DECIMAL(10,4),
    intrinsic_value DECIMAL(10,4),

    -- Additional Options Data
    open_interest INTEGER,

    -- Data Source
    data_source VARCHAR(50) DEFAULT 'IBKR',

    -- Timestamp
    snapshot_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_position_greeks FOREIGN KEY (position_id) REFERENCES ibkr_positions(id)
);

-- 4. Performance History Table (for P&L tracking)
CREATE TABLE IF NOT EXISTS performance_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    position_id UUID NOT NULL REFERENCES ibkr_positions(id) ON DELETE CASCADE,

    -- P&L Metrics
    unrealized_pnl DECIMAL(12,2),
    realized_pnl DECIMAL(12,2),
    total_pnl DECIMAL(12,2),
    pnl_percentage DECIMAL(8,4),

    -- Position Metrics
    current_market_value DECIMAL(12,2),
    days_held INTEGER,
    days_to_expiry INTEGER,

    -- Record Date
    record_date DATE DEFAULT CURRENT_DATE,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_position_performance FOREIGN KEY (position_id) REFERENCES ibkr_positions(id)
);

-- Create Indexes for Performance
CREATE INDEX IF NOT EXISTS idx_ibkr_positions_symbol ON ibkr_positions(ibkr_symbol);
CREATE INDEX IF NOT EXISTS idx_ibkr_positions_trade_id ON ibkr_positions(db_trade_id);
CREATE INDEX IF NOT EXISTS idx_ibkr_positions_expiry ON ibkr_positions(db_options_expiry_date);
CREATE INDEX IF NOT EXISTS idx_ibkr_positions_created ON ibkr_positions(created_at);

CREATE INDEX IF NOT EXISTS idx_market_snapshots_position ON market_snapshots(position_id);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_time ON market_snapshots(snapshot_time);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_source ON market_snapshots(data_source);

CREATE INDEX IF NOT EXISTS idx_options_greeks_position ON options_greeks(position_id);
CREATE INDEX IF NOT EXISTS idx_options_greeks_time ON options_greeks(snapshot_time);

CREATE INDEX IF NOT EXISTS idx_performance_position ON performance_history(position_id);
CREATE INDEX IF NOT EXISTS idx_performance_date ON performance_history(record_date);

-- Create Views for Easy Querying

-- View: Latest Market Data per Position
CREATE OR REPLACE VIEW latest_market_data AS
WITH ranked_data AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY position_id ORDER BY snapshot_time DESC) as rn
    FROM market_snapshots
)
SELECT position_id, current_price, bid_price, ask_price,
       snapshot_time, data_source
FROM ranked_data WHERE rn = 1;

-- View: Latest Greeks per Position
CREATE OR REPLACE VIEW latest_greeks AS
WITH ranked_greeks AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY position_id ORDER BY snapshot_time DESC) as rn
    FROM options_greeks
)
SELECT position_id, delta, gamma, theta, vega, rho,
       implied_volatility, snapshot_time
FROM ranked_greeks WHERE rn = 1;

-- View: Complete Position Summary
CREATE OR REPLACE VIEW position_summary AS
SELECT
    p.*,
    md.current_price as latest_price,
    md.bid_price,
    md.ask_price,
    md.snapshot_time as price_updated_at,
    g.delta,
    g.gamma,
    g.theta,
    g.vega,
    g.implied_volatility,
    g.snapshot_time as greeks_updated_at,
    -- Calculate days to expiry
    CASE
        WHEN p.db_options_expiry_date IS NOT NULL
        THEN p.db_options_expiry_date - CURRENT_DATE
        ELSE NULL
    END as days_to_expiry,
    -- Calculate current P&L if we have latest price
    CASE
        WHEN md.current_price IS NOT NULL AND p.ibkr_avg_cost IS NOT NULL
        THEN (md.current_price - p.ibkr_avg_cost) * p.ibkr_position * 100
        ELSE p.ibkr_unrealized_pnl
    END as current_unrealized_pnl
FROM ibkr_positions p
LEFT JOIN latest_market_data md ON p.id = md.position_id
LEFT JOIN latest_greeks g ON p.id = g.position_id;

-- Function to auto-update updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for auto-updating updated_at
DROP TRIGGER IF EXISTS update_ibkr_positions_updated_at ON ibkr_positions;
CREATE TRIGGER update_ibkr_positions_updated_at
    BEFORE UPDATE ON ibkr_positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Add table comments
COMMENT ON TABLE ibkr_positions IS 'IBKR positions matched with option strategies from database';
COMMENT ON TABLE market_snapshots IS 'Time-series market data snapshots for positions';
COMMENT ON TABLE options_greeks IS 'Time-series options Greeks data';
COMMENT ON TABLE performance_history IS 'Historical P&L tracking for positions';

-- Add column comments
COMMENT ON COLUMN ibkr_positions.db_id IS 'Foreign key to option_strategies.id';
COMMENT ON COLUMN ibkr_positions.db_trade_id IS 'Human-readable trade identifier';
COMMENT ON COLUMN market_snapshots.snapshot_time IS 'When this market data was captured';
COMMENT ON COLUMN options_greeks.snapshot_time IS 'When these Greeks were calculated';
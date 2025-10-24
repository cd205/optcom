-- Migration Script: Modify market_snapshots table for vertical spread tracking
-- Purpose: Enable tracking of spread-level AND individual leg-level metrics over time

-- Drop the existing market_snapshots table and recreate with new structure
-- WARNING: This will delete existing data in market_snapshots table
DROP TABLE IF EXISTS market_snapshots CASCADE;

-- Create the new market_snapshots table with wide format
CREATE TABLE market_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- References to ibkr_positions
    position_id UUID NOT NULL REFERENCES ibkr_positions(id) ON DELETE CASCADE,
    db_trade_id TEXT,

    -- Spread-level metrics (the entire vertical spread)
    spread_market_val DECIMAL(12,2),
    spread_unrealized_pnl DECIMAL(12,2),
    spread_current_price DECIMAL(10,4),

    -- Leg 1 metrics (first option in the spread)
    leg1_symbol VARCHAR(10),
    leg1_description TEXT,
    leg1_market_val DECIMAL(12,2),
    leg1_unrealized_pnl DECIMAL(12,2),
    leg1_current_price DECIMAL(10,4),
    leg1_position DECIMAL(10,2),  -- +1 for long, -1 for short

    -- Leg 2 metrics (second option in the spread)
    leg2_symbol VARCHAR(10),
    leg2_description TEXT,
    leg2_market_val DECIMAL(12,2),
    leg2_unrealized_pnl DECIMAL(12,2),
    leg2_current_price DECIMAL(10,4),
    leg2_position DECIMAL(10,2),  -- +1 for long, -1 for short

    -- Timestamp
    snapshot_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_position_market FOREIGN KEY (position_id) REFERENCES ibkr_positions(id)
);

-- Create indexes for efficient querying
CREATE INDEX idx_market_snapshots_position ON market_snapshots(position_id);
CREATE INDEX idx_market_snapshots_trade_id ON market_snapshots(db_trade_id);
CREATE INDEX idx_market_snapshots_time ON market_snapshots(snapshot_time);
CREATE INDEX idx_market_snapshots_position_time ON market_snapshots(position_id, snapshot_time);

-- Update the latest_market_data view to work with new schema
DROP VIEW IF EXISTS latest_market_data CASCADE;
CREATE OR REPLACE VIEW latest_market_data AS
WITH ranked_data AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY position_id ORDER BY snapshot_time DESC) as rn
    FROM market_snapshots
)
SELECT
    position_id,
    db_trade_id,
    spread_current_price,
    spread_market_val,
    spread_unrealized_pnl,
    leg1_current_price,
    leg2_current_price,
    snapshot_time
FROM ranked_data WHERE rn = 1;

-- Update position_summary view to use new market_snapshots structure
DROP VIEW IF EXISTS position_summary CASCADE;
CREATE OR REPLACE VIEW position_summary AS
SELECT
    p.*,
    md.spread_current_price as latest_spread_price,
    md.spread_market_val as latest_spread_market_val,
    md.spread_unrealized_pnl as latest_spread_pnl,
    md.leg1_current_price as latest_leg1_price,
    md.leg2_current_price as latest_leg2_price,
    md.snapshot_time as price_updated_at,
    -- Calculate days to expiry
    CASE
        WHEN p.db_options_expiry_date IS NOT NULL
        THEN p.db_options_expiry_date - CURRENT_DATE
        ELSE NULL
    END as days_to_expiry
FROM ibkr_positions p
LEFT JOIN latest_market_data md ON p.id = md.position_id;

-- Add table and column comments
COMMENT ON TABLE market_snapshots IS 'Time-series snapshots of vertical spreads and their individual legs';
COMMENT ON COLUMN market_snapshots.position_id IS 'FK to ibkr_positions.id';
COMMENT ON COLUMN market_snapshots.db_trade_id IS 'Trade ID for easy lookup (denormalized from ibkr_positions)';
COMMENT ON COLUMN market_snapshots.spread_market_val IS 'Total market value of the entire spread';
COMMENT ON COLUMN market_snapshots.spread_unrealized_pnl IS 'Unrealized P&L of the entire spread';
COMMENT ON COLUMN market_snapshots.spread_current_price IS 'Net price of the spread (leg1_price + leg2_price considering positions)';
COMMENT ON COLUMN market_snapshots.leg1_market_val IS 'Market value of first leg';
COMMENT ON COLUMN market_snapshots.leg1_unrealized_pnl IS 'Unrealized P&L of first leg';
COMMENT ON COLUMN market_snapshots.leg1_current_price IS 'Current price of first leg';
COMMENT ON COLUMN market_snapshots.leg1_position IS 'Position size of first leg (+1 long, -1 short)';
COMMENT ON COLUMN market_snapshots.leg2_market_val IS 'Market value of second leg';
COMMENT ON COLUMN market_snapshots.leg2_unrealized_pnl IS 'Unrealized P&L of second leg';
COMMENT ON COLUMN market_snapshots.leg2_current_price IS 'Current price of second leg';
COMMENT ON COLUMN market_snapshots.leg2_position IS 'Position size of second leg (+1 long, -1 short)';
COMMENT ON COLUMN market_snapshots.snapshot_time IS 'When this snapshot was captured';

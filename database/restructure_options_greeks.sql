-- SQL Migration: Restructure options_greeks table to match market_snapshots pattern
-- Both legs of a spread are stored on the same row

-- Drop the existing table (backup first if needed)
DROP TABLE IF EXISTS options_greeks CASCADE;

-- Create the new options_greeks table with dual-leg structure
CREATE TABLE options_greeks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    position_id UUID REFERENCES ibkr_positions(id) ON DELETE CASCADE,
    db_trade_id TEXT,
    snapshot_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Spread-level data
    spread_symbol TEXT,
    spread_type TEXT,  -- e.g., "Bull Put", "Bear Call"

    -- Leg 1 - Long/Short leg
    leg1_description TEXT,
    leg1_strike REAL,
    leg1_right TEXT,
    leg1_expiry TEXT,
    leg1_current_price REAL,
    leg1_position REAL,
    -- IBKR Greeks for Leg 1
    leg1_delta REAL,
    leg1_gamma REAL,
    leg1_theta REAL,
    leg1_vega REAL,
    leg1_rho REAL,
    leg1_implied_volatility REAL,
    -- Modelled Greeks for Leg 1
    leg1_delta_modelled REAL,
    leg1_gamma_modelled REAL,
    leg1_theta_modelled REAL,
    leg1_vega_modelled REAL,
    leg1_rho_modelled REAL,
    leg1_implied_volatility_modelled REAL,
    leg1_time_value_modelled REAL,
    leg1_intrinsic_value_modelled REAL,

    -- Leg 2 - Long/Short leg
    leg2_description TEXT,
    leg2_strike REAL,
    leg2_right TEXT,
    leg2_expiry TEXT,
    leg2_current_price REAL,
    leg2_position REAL,
    -- IBKR Greeks for Leg 2
    leg2_delta REAL,
    leg2_gamma REAL,
    leg2_theta REAL,
    leg2_vega REAL,
    leg2_rho REAL,
    leg2_implied_volatility REAL,
    -- Modelled Greeks for Leg 2
    leg2_delta_modelled REAL,
    leg2_gamma_modelled REAL,
    leg2_theta_modelled REAL,
    leg2_vega_modelled REAL,
    leg2_rho_modelled REAL,
    leg2_implied_volatility_modelled REAL,
    leg2_time_value_modelled REAL,
    leg2_intrinsic_value_modelled REAL,

    -- Spread-level Greeks (net of both legs)
    spread_delta REAL,
    spread_gamma REAL,
    spread_theta REAL,
    spread_vega REAL,
    spread_rho REAL,
    spread_delta_modelled REAL,
    spread_gamma_modelled REAL,
    spread_theta_modelled REAL,
    spread_vega_modelled REAL,
    spread_rho_modelled REAL,

    -- Common data
    underlying_price REAL,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_options_greeks_position_id ON options_greeks(position_id);
CREATE INDEX idx_options_greeks_trade_id ON options_greeks(db_trade_id);
CREATE INDEX idx_options_greeks_snapshot_timestamp ON options_greeks(snapshot_timestamp);
CREATE INDEX idx_options_greeks_spread_symbol ON options_greeks(spread_symbol);
CREATE INDEX idx_options_greeks_leg1_desc ON options_greeks(leg1_description);
CREATE INDEX idx_options_greeks_leg2_desc ON options_greeks(leg2_description);

-- Add comments for documentation
COMMENT ON TABLE options_greeks IS 'Stores options Greeks from IBKR (live market data) and Black-Scholes model (fallback) - both legs on same row';
COMMENT ON COLUMN options_greeks.position_id IS 'Foreign key to ibkr_positions table';
COMMENT ON COLUMN options_greeks.db_trade_id IS 'Links to option_strategies.trade_id for cross-reference';
COMMENT ON COLUMN options_greeks.snapshot_timestamp IS 'When the Greeks were captured';
COMMENT ON COLUMN options_greeks.spread_symbol IS 'Underlying symbol for the spread (e.g., AAPL, SPY)';
COMMENT ON COLUMN options_greeks.spread_type IS 'Type of spread (e.g., Bull Put, Bear Call)';
COMMENT ON COLUMN options_greeks.leg1_description IS 'Option contract description for leg 1 (e.g., AAPL 20251031 230.0 P)';
COMMENT ON COLUMN options_greeks.leg2_description IS 'Option contract description for leg 2 (e.g., AAPL 20251031 240.0 P)';
COMMENT ON COLUMN options_greeks.spread_delta IS 'Net delta of the spread (leg1_delta + leg2_delta)';
COMMENT ON COLUMN options_greeks.underlying_price IS 'Underlying stock price at time of Greeks capture';

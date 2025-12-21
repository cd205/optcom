-- SQL Migration: Create/Modify options_greeks table
-- This table stores options Greeks from IBKR (live) and Black-Scholes (modelled)

-- Create the options_greeks table if it doesn't exist
CREATE TABLE IF NOT EXISTS options_greeks (
    id SERIAL PRIMARY KEY,
    position_id INTEGER REFERENCES ibkr_positions(id) ON DELETE CASCADE,
    db_trade_id TEXT,
    leg_description TEXT,
    snapshot_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- IBKR Live Greeks (from market data during market hours)
    delta REAL,
    gamma REAL,
    theta REAL,
    vega REAL,
    rho REAL,
    implied_volatility REAL,
    underlying_price REAL,

    -- Modelled Greeks (Black-Scholes fallback for after-hours/unavailable data)
    delta_modelled REAL,
    gamma_modelled REAL,
    theta_modelled REAL,
    vega_modelled REAL,
    rho_modelled REAL,
    implied_volatility_modelled REAL,
    time_value_modelled REAL,
    intrinsic_value_modelled REAL,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- If table exists, add missing columns
DO $$
BEGIN
    -- Add position_id if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='position_id') THEN
        ALTER TABLE options_greeks ADD COLUMN position_id INTEGER REFERENCES ibkr_positions(id) ON DELETE CASCADE;
    END IF;

    -- Add db_trade_id if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='db_trade_id') THEN
        ALTER TABLE options_greeks ADD COLUMN db_trade_id TEXT;
    END IF;

    -- Add leg_description if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='leg_description') THEN
        ALTER TABLE options_greeks ADD COLUMN leg_description TEXT;
    END IF;

    -- Add snapshot_timestamp if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='snapshot_timestamp') THEN
        ALTER TABLE options_greeks ADD COLUMN snapshot_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
    END IF;

    -- Add IBKR Greeks columns if not exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='delta') THEN
        ALTER TABLE options_greeks ADD COLUMN delta REAL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='gamma') THEN
        ALTER TABLE options_greeks ADD COLUMN gamma REAL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='theta') THEN
        ALTER TABLE options_greeks ADD COLUMN theta REAL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='vega') THEN
        ALTER TABLE options_greeks ADD COLUMN vega REAL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='rho') THEN
        ALTER TABLE options_greeks ADD COLUMN rho REAL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='implied_volatility') THEN
        ALTER TABLE options_greeks ADD COLUMN implied_volatility REAL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='underlying_price') THEN
        ALTER TABLE options_greeks ADD COLUMN underlying_price REAL;
    END IF;

    -- Add Modelled Greeks columns if not exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='delta_modelled') THEN
        ALTER TABLE options_greeks ADD COLUMN delta_modelled REAL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='gamma_modelled') THEN
        ALTER TABLE options_greeks ADD COLUMN gamma_modelled REAL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='theta_modelled') THEN
        ALTER TABLE options_greeks ADD COLUMN theta_modelled REAL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='vega_modelled') THEN
        ALTER TABLE options_greeks ADD COLUMN vega_modelled REAL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='rho_modelled') THEN
        ALTER TABLE options_greeks ADD COLUMN rho_modelled REAL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='implied_volatility_modelled') THEN
        ALTER TABLE options_greeks ADD COLUMN implied_volatility_modelled REAL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='time_value_modelled') THEN
        ALTER TABLE options_greeks ADD COLUMN time_value_modelled REAL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='intrinsic_value_modelled') THEN
        ALTER TABLE options_greeks ADD COLUMN intrinsic_value_modelled REAL;
    END IF;

    -- Add metadata columns if not exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='created_at') THEN
        ALTER TABLE options_greeks ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='options_greeks' AND column_name='updated_at') THEN
        ALTER TABLE options_greeks ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
    END IF;
END $$;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_options_greeks_position_id ON options_greeks(position_id);
CREATE INDEX IF NOT EXISTS idx_options_greeks_trade_id ON options_greeks(db_trade_id);
CREATE INDEX IF NOT EXISTS idx_options_greeks_snapshot_timestamp ON options_greeks(snapshot_timestamp);

-- Add comments for documentation
COMMENT ON TABLE options_greeks IS 'Stores options Greeks from IBKR (live market data) and Black-Scholes model (fallback)';
COMMENT ON COLUMN options_greeks.position_id IS 'Foreign key to ibkr_positions table';
COMMENT ON COLUMN options_greeks.db_trade_id IS 'Links to option_strategies.trade_id for cross-reference';
COMMENT ON COLUMN options_greeks.leg_description IS 'Option contract description (e.g., AAPL 20251031 230.0 P) for joining with market_snapshots';
COMMENT ON COLUMN options_greeks.snapshot_timestamp IS 'When the Greeks were captured';
COMMENT ON COLUMN options_greeks.delta IS 'Delta from IBKR (rate of change of option price vs underlying)';
COMMENT ON COLUMN options_greeks.gamma IS 'Gamma from IBKR (rate of change of delta)';
COMMENT ON COLUMN options_greeks.theta IS 'Theta from IBKR (time decay per day)';
COMMENT ON COLUMN options_greeks.vega IS 'Vega from IBKR (sensitivity to volatility)';
COMMENT ON COLUMN options_greeks.rho IS 'Rho from IBKR (sensitivity to interest rates)';
COMMENT ON COLUMN options_greeks.implied_volatility IS 'Market-based implied volatility from IBKR';
COMMENT ON COLUMN options_greeks.underlying_price IS 'Underlying stock price at time of Greeks capture';
COMMENT ON COLUMN options_greeks.delta_modelled IS 'Black-Scholes calculated delta (fallback)';
COMMENT ON COLUMN options_greeks.gamma_modelled IS 'Black-Scholes calculated gamma (fallback)';
COMMENT ON COLUMN options_greeks.theta_modelled IS 'Black-Scholes calculated theta (fallback)';
COMMENT ON COLUMN options_greeks.vega_modelled IS 'Black-Scholes calculated vega (fallback)';
COMMENT ON COLUMN options_greeks.rho_modelled IS 'Black-Scholes calculated rho (fallback)';
COMMENT ON COLUMN options_greeks.implied_volatility_modelled IS 'Estimated IV used for Black-Scholes (fallback)';
COMMENT ON COLUMN options_greeks.time_value_modelled IS 'Time value from Black-Scholes calculation';
COMMENT ON COLUMN options_greeks.intrinsic_value_modelled IS 'Intrinsic value from Black-Scholes calculation';

# Market Snapshots Implementation Guide

## Overview

This implementation allows you to track the price history and P&L of vertical option spreads over time, with the ability to graph both the spread as a whole and its individual legs.

## Database Schema Changes

### Modified `market_snapshots` Table

The new schema uses a **wide table format** that stores spread-level and leg-level metrics in a single row per snapshot:

```
market_snapshots
├── id (UUID, primary key)
├── position_id (UUID, FK to ibkr_positions.id)
├── db_trade_id (TEXT, denormalized for easy lookup)
│
├── Spread-level metrics:
│   ├── spread_market_val
│   ├── spread_unrealized_pnl
│   └── spread_current_price
│
├── Leg 1 metrics:
│   ├── leg1_symbol
│   ├── leg1_description
│   ├── leg1_market_val
│   ├── leg1_unrealized_pnl
│   ├── leg1_current_price
│   └── leg1_position
│
├── Leg 2 metrics:
│   ├── leg2_symbol
│   ├── leg2_description
│   ├── leg2_market_val
│   ├── leg2_unrealized_pnl
│   ├── leg2_current_price
│   └── leg2_position
│
└── snapshot_time (TIMESTAMP)
```

### Key Design Decisions

1. **Wide format**: All spread and leg data in one row for easier querying and graphing
2. **Denormalized `db_trade_id`**: Allows fast lookups without joins
3. **Leg descriptions**: Identifies which strike/expiry each leg represents
4. **Position tracking**: Stores whether each leg is long (+1) or short (-1)

## Installation Steps

### 1. Apply Database Migration

Run the SQL migration to update the schema:

```bash
psql -h 127.0.0.1 -p 5433 -U your_user -d your_database -f /home/cdodd/optcom/database/modify_market_snapshots.sql
```

**WARNING**: This will drop and recreate the `market_snapshots` table, deleting any existing data.

### 2. Install Python Dependencies

Ensure you have the required packages:

```bash
pip install pandas psycopg2-binary matplotlib
```

## Usage

### Collecting Market Snapshots

The market snapshot collection integrates with your existing IBKR notebook workflow.

#### In your notebook, add:

```python
# At the top of the notebook
import sys
sys.path.insert(0, '/home/cdodd/optcom')
from notebook_snapshot_integration import capture_market_snapshots
```

#### After your existing IBKR data collection:

```python
# ... existing code to connect to IBKR and get positions ...

if not spreads_df.empty and not db_strategies_df.empty:
    joined_df = join_spreads_with_database(spreads_df, db_strategies_df)

    if not joined_df.empty:
        # Insert positions
        success = insert_positions_to_database(joined_df)

        # NEW: Capture market snapshots
        snapshots_created = capture_market_snapshots(
            positions_df, spreads_df, joined_df, pg_creds
        )
        print(f"Captured {snapshots_created} market snapshots")
```

### Visualizing Position History

#### Plot a single metric:

```python
from market_snapshot_utils import plot_position_history
import matplotlib.pyplot as plt

# By trade_id (recommended)
fig = plot_position_history(
    position_identifier='AAPL_BullPut_230_240_20251031',
    pg_creds=pg_creds,
    use_trade_id=True,
    metric='unrealized_pnl'  # Options: 'unrealized_pnl', 'market_val', 'current_price'
)
plt.show()

# Or by position UUID
fig = plot_position_history(
    position_identifier='550e8400-e29b-41d4-a716-446655440000',
    pg_creds=pg_creds,
    use_trade_id=False,
    metric='market_val'
)
plt.show()
```

#### Plot multiple metrics:

```python
trade_id = 'AAPL_BullPut_230_240_20251031'

fig1 = plot_position_history(trade_id, pg_creds, metric='unrealized_pnl')
fig2 = plot_position_history(trade_id, pg_creds, metric='market_val')
fig3 = plot_position_history(trade_id, pg_creds, metric='current_price')

plt.show()
```

### Graph Features

The plotting function includes:

- **Spread line** (thick blue line) - Shows the entire spread's metrics
- **Leg 1 line** (dashed magenta line) - Individual leg metrics
- **Leg 2 line** (dashed orange line) - Individual leg metrics
- **Expiry vertical line** (red dotted) - Marks the option expiration date
- **X-axis range** - Automatically spans from position open date to expiry
- **Zero line** (for P&L charts) - Shows break-even point

## Data Flow

```
IBKR TWS/Gateway
      ↓
get_positions_data() → positions_df (individual options)
get_account_updates() → updates prices/P&L
      ↓
find_vertical_spreads() → spreads_df (matched spreads)
      ↓
join_spreads_with_database() → joined_df (matched with DB strategies)
      ↓
insert_positions_to_database() → Updates ibkr_positions table
      ↓
capture_market_snapshots() → Creates time-series records in market_snapshots
      ↓
plot_position_history() → Visualizes historical data
```

## Querying Snapshot Data

### Get all snapshots for a position:

```sql
SELECT
    snapshot_time,
    spread_unrealized_pnl,
    leg1_current_price,
    leg2_current_price
FROM market_snapshots
WHERE db_trade_id = 'AAPL_BullPut_230_240_20251031'
ORDER BY snapshot_time ASC;
```

### Get latest snapshot for all positions:

```sql
SELECT * FROM latest_market_data;
```

### Compare entry vs current metrics:

```sql
SELECT
    p.ibkr_description,
    p.ibkr_avg_cost as entry_cost,
    m.spread_current_price as current_cost,
    p.ibkr_unrealized_pnl as total_pnl,
    m.snapshot_time as last_updated
FROM ibkr_positions p
JOIN latest_market_data m ON p.id = m.position_id;
```

## File Reference

| File | Purpose |
|------|---------|
| [database/modify_market_snapshots.sql](database/modify_market_snapshots.sql) | SQL migration script |
| [market_snapshot_utils.py](market_snapshot_utils.py) | Core snapshot and plotting functions |
| [notebook_snapshot_integration.py](notebook_snapshot_integration.py) | Notebook integration code |
| [ikbr_get_positions_streamlined.ipynb](ikbr_get_positions_streamlined.ipynb) | Main IBKR data collection notebook |

## Scheduling Automated Snapshots

To build historical data, run the notebook on a schedule:

### Using cron (Linux):

```bash
# Run every hour during market hours (9:30 AM - 4:00 PM EST, Mon-Fri)
30 9-16 * * 1-5 cd /home/cdodd/optcom && jupyter nbconvert --to notebook --execute ikbr_get_positions_streamlined.ipynb
```

### Using Windows Task Scheduler:

Create a task that runs:
```
jupyter nbconvert --to notebook --execute ikbr_get_positions_streamlined.ipynb
```

## Troubleshooting

### "No snapshot data found"
- Check that the position exists in `ibkr_positions`
- Verify `db_trade_id` matches exactly
- Ensure snapshots have been captured (run the notebook at least once after migration)

### "Could not find both legs"
- Verify the spread description format matches expected pattern
- Check that both individual legs exist in `positions_df`
- Ensure strike prices match exactly

### Database connection errors
- Verify PostgreSQL is running
- Check `pg_creds` configuration
- Ensure port forwarding is active (if using WSL)

## Next Steps

1. Apply the database migration
2. Update your notebook with snapshot capture code
3. Run the notebook once to create initial snapshots
4. Set up scheduled execution for ongoing tracking
5. Use the plotting functions to analyze your positions

## Questions?

Refer to the function docstrings in the Python files for detailed parameter descriptions and usage examples.

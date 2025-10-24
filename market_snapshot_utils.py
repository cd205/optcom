"""
Utility functions for market snapshot tracking and visualization
"""
import pandas as pd
import psycopg2
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from typing import Optional, Tuple


def insert_market_snapshot(
    position_id: str,
    db_trade_id: str,
    spread_data: dict,
    leg1_data: dict,
    leg2_data: dict,
    pg_creds: dict,
    snapshot_time: Optional[datetime] = None
) -> bool:
    """
    Insert a market snapshot for a vertical spread position.

    Args:
        position_id: UUID from ibkr_positions.id
        db_trade_id: Trade ID from ibkr_positions.db_trade_id
        spread_data: Dict with keys: market_val, unrealized_pnl, current_price
        leg1_data: Dict with keys: symbol, description, market_val, unrealized_pnl, current_price, position
        leg2_data: Dict with keys: symbol, description, market_val, unrealized_pnl, current_price, position
        pg_creds: Database credentials dict
        snapshot_time: Optional timestamp (defaults to CURRENT_TIMESTAMP)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        conn = psycopg2.connect(
            host=pg_creds['host'],
            port=pg_creds['port'],
            database=pg_creds['database'],
            user=pg_creds['user'],
            password=pg_creds['password']
        )

        cursor = conn.cursor()

        if snapshot_time:
            insert_sql = """
            INSERT INTO market_snapshots (
                position_id, db_trade_id,
                spread_market_val, spread_unrealized_pnl, spread_current_price,
                leg1_symbol, leg1_description, leg1_market_val, leg1_unrealized_pnl,
                leg1_current_price, leg1_position,
                leg2_symbol, leg2_description, leg2_market_val, leg2_unrealized_pnl,
                leg2_current_price, leg2_position,
                snapshot_time
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
            values = (
                position_id, db_trade_id,
                spread_data.get('market_val'), spread_data.get('unrealized_pnl'),
                spread_data.get('current_price'),
                leg1_data.get('symbol'), leg1_data.get('description'),
                leg1_data.get('market_val'), leg1_data.get('unrealized_pnl'),
                leg1_data.get('current_price'), leg1_data.get('position'),
                leg2_data.get('symbol'), leg2_data.get('description'),
                leg2_data.get('market_val'), leg2_data.get('unrealized_pnl'),
                leg2_data.get('current_price'), leg2_data.get('position'),
                snapshot_time
            )
        else:
            insert_sql = """
            INSERT INTO market_snapshots (
                position_id, db_trade_id,
                spread_market_val, spread_unrealized_pnl, spread_current_price,
                leg1_symbol, leg1_description, leg1_market_val, leg1_unrealized_pnl,
                leg1_current_price, leg1_position,
                leg2_symbol, leg2_description, leg2_market_val, leg2_unrealized_pnl,
                leg2_current_price, leg2_position
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
            values = (
                position_id, db_trade_id,
                spread_data.get('market_val'), spread_data.get('unrealized_pnl'),
                spread_data.get('current_price'),
                leg1_data.get('symbol'), leg1_data.get('description'),
                leg1_data.get('market_val'), leg1_data.get('unrealized_pnl'),
                leg1_data.get('current_price'), leg1_data.get('position'),
                leg2_data.get('symbol'), leg2_data.get('description'),
                leg2_data.get('market_val'), leg2_data.get('unrealized_pnl'),
                leg2_data.get('current_price'), leg2_data.get('position')
            )

        cursor.execute(insert_sql, values)
        conn.commit()
        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print(f"Failed to insert market snapshot: {e}")
        return False


def create_snapshots_from_ibkr_data(
    positions_df: pd.DataFrame,
    spreads_df: pd.DataFrame,
    joined_df: pd.DataFrame,
    pg_creds: dict
) -> int:
    """
    Create market snapshots from IBKR position data.

    This function processes spread data and individual leg data from the notebook
    and creates snapshot records in the database.

    Args:
        positions_df: DataFrame from get_positions_dataframe() containing individual legs
        spreads_df: DataFrame from find_vertical_spreads() containing spread data
        joined_df: DataFrame from join_spreads_with_database() containing position IDs
        pg_creds: Database credentials dict

    Returns:
        int: Number of snapshots created
    """
    snapshots_created = 0

    for _, spread_row in joined_df.iterrows():
        # Get the position_id from the database
        position_id = spread_row.get('position_id')  # This needs to be added to joined_df
        db_trade_id = spread_row['db_trade_id']

        # Extract spread data
        spread_data = {
            'market_val': spread_row.get('ibkr_market_val'),
            'unrealized_pnl': spread_row.get('ibkr_unrealized_pnl'),
            'current_price': spread_row.get('ibkr_current_price')
        }

        # Parse the spread description to find the individual legs
        description = spread_row['ibkr_description']
        symbol = spread_row['ibkr_symbol']

        # Extract strike prices from description (e.g., "Bull Put 230.0/240.0 20251031")
        parts = description.split()
        strike_info = parts[2]
        expiry = parts[3]
        strikes = strike_info.split('/')
        strike1, strike2 = float(strikes[0]), float(strikes[1])

        # Determine right (Call/Put) from description
        right = 'P' if 'Put' in description else 'C'

        # Find the individual legs in positions_df
        leg1 = positions_df[
            (positions_df['Symbol'] == symbol) &
            (positions_df['Strike'] == strike1) &
            (positions_df['Right'] == right) &
            (positions_df['Expiry'] == expiry)
        ]

        leg2 = positions_df[
            (positions_df['Symbol'] == symbol) &
            (positions_df['Strike'] == strike2) &
            (positions_df['Right'] == right) &
            (positions_df['Expiry'] == expiry)
        ]

        if not leg1.empty and not leg2.empty:
            leg1_row = leg1.iloc[0]
            leg2_row = leg2.iloc[0]

            leg1_data = {
                'symbol': leg1_row['Symbol'],
                'description': leg1_row['Description'],
                'market_val': leg1_row['MarketVal'],
                'unrealized_pnl': leg1_row['UnrealizedPnL'],
                'current_price': leg1_row['CurrentPrice'],
                'position': leg1_row['Position']
            }

            leg2_data = {
                'symbol': leg2_row['Symbol'],
                'description': leg2_row['Description'],
                'market_val': leg2_row['MarketVal'],
                'unrealized_pnl': leg2_row['UnrealizedPnL'],
                'current_price': leg2_row['CurrentPrice'],
                'position': leg2_row['Position']
            }

            # Insert the snapshot
            if position_id and insert_market_snapshot(
                position_id, db_trade_id, spread_data, leg1_data, leg2_data, pg_creds
            ):
                snapshots_created += 1

    return snapshots_created


def get_snapshot_history(
    position_identifier: str,
    pg_creds: dict,
    use_trade_id: bool = True
) -> pd.DataFrame:
    """
    Retrieve snapshot history for a position.

    Args:
        position_identifier: Either db_trade_id or position_id (UUID)
        pg_creds: Database credentials dict
        use_trade_id: If True, treats identifier as db_trade_id, else as position_id

    Returns:
        DataFrame with snapshot history
    """
    try:
        conn = psycopg2.connect(
            host=pg_creds['host'],
            port=pg_creds['port'],
            database=pg_creds['database'],
            user=pg_creds['user'],
            password=pg_creds['password']
        )

        if use_trade_id:
            query = """
            SELECT * FROM market_snapshots
            WHERE db_trade_id = %s
            ORDER BY snapshot_time ASC
            """
        else:
            query = """
            SELECT * FROM market_snapshots
            WHERE position_id = %s
            ORDER BY snapshot_time ASC
            """

        df = pd.read_sql_query(query, conn, params=(position_identifier,))
        conn.close()
        return df

    except Exception as e:
        print(f"Failed to retrieve snapshot history: {e}")
        return pd.DataFrame()


def plot_position_history(
    position_identifier: str,
    pg_creds: dict,
    use_trade_id: bool = True,
    metric: str = 'unrealized_pnl',
    figsize: Tuple[int, int] = (14, 8)
) -> plt.Figure:
    """
    Plot the price/P&L history of a vertical spread and its legs.

    Args:
        position_identifier: Either db_trade_id or position_id (UUID)
        pg_creds: Database credentials dict
        use_trade_id: If True, treats identifier as db_trade_id, else as position_id
        metric: Which metric to plot ('unrealized_pnl', 'market_val', or 'current_price')
        figsize: Figure size as (width, height)

    Returns:
        matplotlib Figure object
    """
    # Get snapshot history
    snapshots_df = get_snapshot_history(position_identifier, pg_creds, use_trade_id)

    if snapshots_df.empty:
        print(f"No snapshot data found for {position_identifier}")
        return None

    # Get position details for expiry date
    conn = psycopg2.connect(
        host=pg_creds['host'],
        port=pg_creds['port'],
        database=pg_creds['database'],
        user=pg_creds['user'],
        password=pg_creds['password']
    )

    if use_trade_id:
        position_query = """
        SELECT db_options_expiry_date, created_at, ibkr_description, ibkr_symbol
        FROM ibkr_positions
        WHERE db_trade_id = %s
        LIMIT 1
        """
    else:
        position_query = """
        SELECT db_options_expiry_date, created_at, ibkr_description, ibkr_symbol
        FROM ibkr_positions
        WHERE id = %s
        LIMIT 1
        """

    position_info = pd.read_sql_query(position_query, conn, params=(position_identifier,))
    conn.close()

    if position_info.empty:
        print(f"Position not found: {position_identifier}")
        return None

    expiry_date = pd.to_datetime(position_info['db_options_expiry_date'].iloc[0])
    position_opened = pd.to_datetime(position_info['created_at'].iloc[0])
    description = position_info['ibkr_description'].iloc[0]
    symbol = position_info['ibkr_symbol'].iloc[0]

    # Create the plot
    fig, ax = plt.subplots(figsize=figsize)

    # Convert snapshot_time to datetime
    snapshots_df['snapshot_time'] = pd.to_datetime(snapshots_df['snapshot_time'])

    # Determine column names based on metric
    if metric == 'unrealized_pnl':
        spread_col = 'spread_unrealized_pnl'
        leg1_col = 'leg1_unrealized_pnl'
        leg2_col = 'leg2_unrealized_pnl'
        ylabel = 'Unrealized P&L ($)'
        title_metric = 'Unrealized P&L'
    elif metric == 'market_val':
        spread_col = 'spread_market_val'
        leg1_col = 'leg1_market_val'
        leg2_col = 'leg2_market_val'
        ylabel = 'Market Value ($)'
        title_metric = 'Market Value'
    elif metric == 'current_price':
        spread_col = 'spread_current_price'
        leg1_col = 'leg1_current_price'
        leg2_col = 'leg2_current_price'
        ylabel = 'Price ($)'
        title_metric = 'Price'
    else:
        raise ValueError(f"Unknown metric: {metric}")

    # Plot spread and legs
    ax.plot(snapshots_df['snapshot_time'], snapshots_df[spread_col],
            label='Spread', linewidth=2.5, marker='o', color='#2E86AB')
    ax.plot(snapshots_df['snapshot_time'], snapshots_df[leg1_col],
            label=f"Leg 1: {snapshots_df['leg1_description'].iloc[0]}",
            linewidth=1.5, marker='s', linestyle='--', color='#A23B72', alpha=0.7)
    ax.plot(snapshots_df['snapshot_time'], snapshots_df[leg2_col],
            label=f"Leg 2: {snapshots_df['leg2_description'].iloc[0]}",
            linewidth=1.5, marker='^', linestyle='--', color='#F18F01', alpha=0.7)

    # Add vertical line for expiry date
    ax.axvline(x=expiry_date, color='red', linestyle=':', linewidth=2,
               label=f'Expiry: {expiry_date.strftime("%Y-%m-%d")}', alpha=0.7)

    # Add horizontal line at zero for P&L charts
    if metric == 'unrealized_pnl':
        ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5, alpha=0.5)

    # Formatting
    ax.set_xlabel('Date', fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(f'{title_metric} History: {symbol} {description}', fontsize=14, fontweight='bold')
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)

    # Format x-axis dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.xticks(rotation=45, ha='right')

    # Set x-axis limits from position open to expiry (or latest data if after expiry)
    max_date = max(expiry_date, snapshots_df['snapshot_time'].max())
    ax.set_xlim(position_opened, max_date)

    plt.tight_layout()
    return fig


# Example usage in notebook:
"""
# After running the IBKR data collection in the notebook:

from market_snapshot_utils import create_snapshots_from_ibkr_data, plot_position_history

# Create snapshots from current data
# Note: You'll need to modify join_spreads_with_database to also return position_id
snapshots_created = create_snapshots_from_ibkr_data(
    positions_df, spreads_df, joined_df, pg_creds
)
print(f"Created {snapshots_created} market snapshots")

# Plot a specific position's history
fig = plot_position_history(
    position_identifier='AAPL_BullPut_230_240_20251031',  # Your db_trade_id
    pg_creds=pg_creds,
    use_trade_id=True,
    metric='unrealized_pnl'  # or 'market_val' or 'current_price'
)
plt.show()

# Or plot by position UUID
fig = plot_position_history(
    position_identifier='550e8400-e29b-41d4-a716-446655440000',
    pg_creds=pg_creds,
    use_trade_id=False,
    metric='market_val'
)
plt.show()
"""

import matplotlib
matplotlib.use('Agg') # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import io
from datetime import datetime
import polymarket_api as api

def parse_market_date(date_str):
    """Attempts to parse a date string like 'January 31' to a datetime; returns None on failure."""
    try:
        current_year = datetime.now().year
        full_date_str = f"{date_str} {current_year}"
        return datetime.strptime(full_date_str, "%B %d %Y")
    except ValueError:
        return None

def is_market_closed(market):
    """Heuristic to determine if a market is closed/resolved."""
    status = str(market.get('status', '')).lower()
    closed_flag = market.get('closed') or market.get('isResolved')
    return closed_flag or status in {"closed", "resolved", "finalized"}

def generate_report(event_url, weekly=False):
    """
    Main orchestrator.
    1. Fetches markets from URL.
    2. Plots all markets found for the event.
    3. Generates Plot & Table.
    
    Returns: (image_buffer, text_response)
    """
    markets = api.get_event_markets(event_url)
    if not markets:
        return None, "Could not fetch event markets. Check the URL."

    # 1. Collect open markets with a display title and optional parsed date
    today = datetime.now().date()
    valid_markets = []
    for m in markets:
        if is_market_closed(m):
            continue
        title = m.get('groupItemTitle', m.get('question', 'Unknown'))
        volume = m.get('volume', 'N/A')
        parsed_dt = parse_market_date(title)
        if parsed_dt and parsed_dt.date() <= today:
            # skip dates that are today or in the past
            continue
        valid_markets.append((m, title, parsed_dt, volume))
    
    if not valid_markets:
        return None, "No open future markets found for this event."

    # 2. Order markets: dated (soonest first) then undated, limit to 5
    dated = [item for item in valid_markets if item[2]]
    undated = [item for item in valid_markets if not item[2]]
    dated = sorted(dated, key=lambda x: x[2])
    ordered_markets = (dated + undated)#[:7]

    
    table_rows = []

    plot_data = []

    for i, (market, title, parsed_dt, volume) in enumerate(ordered_markets):
        group_date = title
        if parsed_dt:
            group_date = f"{title} ({parsed_dt.strftime('%Y-%m-%d')})"
        print(f"DEBUG: Processing Market {i+1}: '{title}' with volume {volume}")
        # Resolve Token ID
        yes_token_id = api.get_yes_token_id(market)
        if not yes_token_id:
            # Fallback: fetch full details if missing in summary
            slug = market.get('slug')
            if slug:
                full = api.fetch_full_market_details(slug, debug=False)
                if full:
                    volume = full.get('volume', 'N/A')  # Update volume if available
        
                    try:
                        volume = int(volume)
                    except:
                        volume = 'N/A'

                    
                    yes_token_id = api.get_yes_token_id(full)
        
        current_val_str = "N/A"
        
        try:
            volume = float(volume)
            volume = int(volume)
        except:
            volume = 'N/A'

        if volume != 'N/A':
            # Format volume for display with thousands separator and K suffixes
            volume_str = f"${volume:,}"
            if volume >= 1_000_000:
                volume_str = f"${volume/1_000_000:.1f}M"
            elif volume >= 1_000:
                volume_str = f"${volume/1_000:.2f}K"
            volume = volume_str
        
        if yes_token_id:
            history = api.get_price_history(yes_token_id, debug=False, weekly=weekly)
            if history:
                df = pd.DataFrame(history)
                df['t'] = pd.to_datetime(df['t'], unit='s')
                df['p'] = df['p'] * 100
                df = df.sort_values('t')

                # Annotate Current Value
                current_val = df['p'].iloc[-1]
                current_val_str = f"{current_val:.1f}%"

                plot_data.append((group_date, df, current_val, current_val_str, volume))

        # Add to table
        table_rows.append(f"{group_date:<24} | {current_val_str:<6} | {volume:<8}")
    
    
    # 3. Setup Plot for selected markets
    n = len(plot_data) if len(plot_data) < 7 else 7
    fig_height = max(3, n) * 2.5  # scale height with market count
    fig, axs = plt.subplots(n, 1, figsize=(10, fig_height))
    if n == 1:
        axs = [axs]
    fig.suptitle("Polymarket Odds History", fontsize=16, fontweight='bold')
    fig.subplots_adjust(hspace=0.8, top=0.92)

    for ax, (group_date, df, current_val, current_val_str, volume) in zip(axs, plot_data):
        ax.plot(df['t'], df['p'], linewidth=2, color='#007bff')
        
        ax.axhline(y=current_val, color='red', linestyle=':', alpha=0.8)
        x_pos = df['t'].iloc[-1]
        ax.text(x_pos + pd.Timedelta(minutes=10), current_val, current_val_str, 
                color='red', fontweight='bold', ha='left', va='bottom')

        ax.set_title(f"{group_date}     [{volume}]", loc='left', fontsize=12)
        ax.set_ylabel("Prob (%)")
        ax.grid(True, linestyle='--', alpha=0.5)
        if weekly:
            ax.set_xlim((df['t'].max() - pd.Timedelta(days=8), df['t'].max() + pd.Timedelta(hours=8)))
            ax.xaxis.set_major_locator(mdates.DayLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))

    # Save
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close()

    # Build Table String
    table_header = f"{'Market':<24} | {'Prob':<6} | {'Volume':<8}"
    table_divider = "-" * len(table_header)
    table_text = f"```\n{table_header}\n{table_divider}\n"
    table_text += "\n".join(table_rows)
    table_text += "\n```"

    return buf, table_text
import matplotlib
matplotlib.use('Agg') # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import io
import calendar
from datetime import datetime, timedelta
import polymarket_api as api

def parse_market_date(date_str):
    """Attempts to parse a date string like 'January 31' to a datetime object."""
    try:
        current_year = datetime.now().year
        full_date_str = f"{date_str} {current_year}"
        dt = datetime.strptime(full_date_str, "%B %d %Y")
        return dt
    except ValueError:
        return None

def get_closest_market(market_list, target_date):
    """Finds the market in the list closest to the target_date."""
    if not market_list:
        return None
    # market_list items are tuples: (market_data, parsed_date)
    closest = min(market_list, key=lambda x: abs((x[1] - target_date).total_seconds()))
    return closest

def generate_report(event_url):
    """
    Main orchestrator.
    1. Fetches markets from URL.
    2. Filters for Today, Next Week, Month End.
    3. Generates Plot & Table.
    
    Returns: (image_buffer, text_response)
    """
    markets = api.get_event_markets(event_url)
    if not markets:
        return None, "Could not fetch event markets. Check the URL."

    # 1. Parse dates
    valid_markets = []
    for m in markets:
        title = m.get('groupItemTitle', m.get('question', 'Unknown'))
        dt = parse_market_date(title)
        if dt:
            valid_markets.append((m, dt))
    
    if not valid_markets:
        return None, "Could not parse dates for any markets in this event."

    # 2. Determine Targets
    now = datetime.now()
    target_today = now
    target_week = now + timedelta(days=7)
    last_day = calendar.monthrange(now.year, now.month)[1]
    target_month_end = now.replace(day=last_day)

    # 3. Select Markets
    selected_markets = [
        ("Closest to Today", get_closest_market(valid_markets, target_today)),
        ("Next Week", get_closest_market(valid_markets, target_week)),
        ("Month End", get_closest_market(valid_markets, target_month_end))
    ]

    # 4. Setup Plot
    fig, axs = plt.subplots(3, 1, figsize=(10, 8), constrained_layout=True)
    fig.suptitle(f"Polymarket Odds History (Last 24h)", fontsize=16, fontweight='bold')

    table_rows = []

    for ax, (label, (market, dt)) in zip(axs, selected_markets):
        group_date = market.get('groupItemTitle', market.get('question', 'Unknown'))
        
        # Resolve Token ID
        yes_token_id = api.get_yes_token_id(market)
        if not yes_token_id:
            # Fallback: fetch full details if missing in summary
            slug = market.get('slug')
            if slug:
                full = api.fetch_full_market_details(slug)
                if full:
                    yes_token_id = api.get_yes_token_id(full)
        
        current_val_str = "N/A"
        
        if yes_token_id:
            history = api.get_price_history(yes_token_id)
            if history:
                df = pd.DataFrame(history)
                df['t'] = pd.to_datetime(df['t'], unit='s')
                df['p'] = df['p'] * 100
                df = df.sort_values('t')

                # Plot
                ax.plot(df['t'], df['p'], label=f"{group_date}", linewidth=2, color='#007bff')
                
                # Annotate Current Value
                current_val = df['p'].iloc[-1]
                current_val_str = f"{current_val:.1f}%"
                
                ax.axhline(y=current_val, color='red', linestyle=':', alpha=0.8)
                x_pos = df['t'].iloc[-1]
                ax.text(x_pos, current_val + 0.5, current_val_str, 
                        color='red', fontweight='bold', ha='left', va='bottom')

                ax.set_title(f"{label}: {group_date}", loc='left', fontsize=12)
                ax.set_ylabel("Prob (%)")
                ax.grid(True, linestyle='--', alpha=0.5)
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            else:
                ax.text(0.5, 0.5, "No History", ha='center', va='center')
        else:
            ax.text(0.5, 0.5, "Data Unavailable", ha='center', va='center')

        # Add to table
        table_rows.append(f"{label:<16} | {group_date:<12} | {current_val_str}")

    # Save to buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close()

    # Build Table String
    table_header = f"{'Target':<16} | {'Date':<12} | {'Prob':<6}"
    table_divider = "-" * len(table_header)
    table_text = f"```\n{table_header}\n{table_divider}\n"
    table_text += "\n".join(table_rows)
    table_text += "\n```"

    return buf, table_text
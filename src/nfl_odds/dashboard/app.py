import streamlit as st
import polars as pl
import pandas as pd
import numpy as np
from nfl_odds.models.train import PlayerPropModel
from nfl_odds.betting.ev_calc import calculate_implied_probability, calculate_ev, calculate_edge

st.set_page_config(page_title="NFL Player Prop Analytics", layout="wide")

def load_bugatti_design():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=JetBrains+Mono:wght@400&family=Saira+Condensed:wght@400;600&display=swap');

        :root {
            --canvas: #000000;
            --surface-card: #141414;
            --primary: #ffffff;
            --link: #c3d9f3;
            --muted: #999999;
            --hairline: #262626;
            --hairline-strong: #3a3a3a;
            --font-display: "Saira Condensed", sans-serif;
            --font-body: "Cormorant Garamond", serif;
            --font-mono: "JetBrains Mono", monospace;
        }

        /* Base app background and text */
        .stApp, .stApp > header {
            background-color: var(--canvas) !important;
            color: var(--primary) !important;
            font-family: var(--font-body) !important;
        }

        /* Ensure all standard paragraphs, divs, and spans use the serif body font, except when overridden */
        div.stMarkdown p, div.stMarkdown span, div.stMarkdown li, .stMarkdown {
            font-family: var(--font-body) !important;
            font-size: 16px !important;
            line-height: 1.5 !important;
            letter-spacing: 0px !important;
            color: #cccccc !important; /* Body color from DESIGN.md */
        }

        /* Display Fonts - Headers */
        h1, h2, h3, h4, h5, h6, 
        .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4, .stMarkdown h5, .stMarkdown h6 {
            font-family: var(--font-display) !important;
            text-transform: uppercase !important;
            font-weight: 400 !important;
            color: var(--primary) !important;
            margin-bottom: 24px !important;
        }

        .stMarkdown h1, h1 {
            font-size: 64px !important;
            letter-spacing: 4px !important;
            line-height: 1.1 !important;
            padding-bottom: 32px !important;
            padding-top: 120px !important; /* Spacing section */
        }
        
        .stMarkdown h2, h2 {
            font-size: 48px !important;
            letter-spacing: 3px !important;
            line-height: 1.15 !important;
            padding-top: 64px !important;
        }
        
        .stMarkdown h3, h3 {
            font-size: 32px !important;
            letter-spacing: 2px !important;
            line-height: 1.2 !important;
        }

        /* Hide Streamlit top padding and block spacing */
        .block-container {
            padding-top: 0px !important;
            max-width: 1280px !important;
        }

        /* Buttons - Bugatti Monospace, pill shaped, transparent */
        .stButton > button, div[data-testid="stButton"] button {
            background-color: transparent !important;
            color: var(--primary) !important;
            border: 1px solid var(--primary) !important;
            border-radius: 9999px !important;
            font-family: var(--font-mono) !important;
            text-transform: uppercase !important;
            letter-spacing: 2.5px !important;
            font-size: 14px !important;
            padding: 14px 32px !important;
            height: 44px !important;
            font-weight: 400 !important;
            box-shadow: none !important;
            line-height: 1 !important;
        }
        .stButton > button:hover, div[data-testid="stButton"] button:hover {
            background-color: rgba(255,255,255,0.05) !important;
            color: var(--primary) !important;
            border-color: var(--primary) !important;
        }

        /* Inputs & Selects - transparent, flat, bottom border only */
        .stSelectbox > div > div, 
        .stTextInput > div > div, 
        .stNumberInput > div > div {
            background-color: transparent !important;
            color: var(--primary) !important;
            border: none !important;
            border-bottom: 1px solid var(--hairline-strong) !important;
            border-radius: 0px !important;
            box-shadow: none !important;
            font-family: var(--font-body) !important;
        }
        .stSelectbox label p, .stTextInput label p, .stNumberInput label p {
            font-family: var(--font-mono) !important;
            text-transform: uppercase !important;
            letter-spacing: 2px !important;
            font-size: 11px !important;
            color: var(--primary) !important;
        }

        /* Sidebar */
        section[data-testid="stSidebar"] {
            background-color: var(--surface-card) !important;
            border-right: 1px solid var(--hairline) !important;
        }
        
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            font-family: var(--font-mono) !important;
            text-transform: uppercase !important;
            letter-spacing: 2px !important;
            font-size: 12px !important;
        }

        /* Metrics */
        div[data-testid="stMetricValue"] {
            font-family: var(--font-display) !important;
            font-size: 32px !important;
            font-weight: 400 !important;
            letter-spacing: 2px !important;
            color: var(--primary) !important;
        }
        div[data-testid="stMetricLabel"] * {
            font-family: var(--font-mono) !important;
            text-transform: uppercase !important;
            letter-spacing: 2px !important;
            color: var(--muted) !important;
            font-size: 11px !important;
        }
        div[data-testid="stMetricDelta"] * {
            font-family: var(--font-mono) !important;
        }

        /* Alerts / Status boxes */
        div[data-testid="stAlert"] {
            --hairline: #333333;
            --success: #00ff88;
            --error: #ff3366;
            --font-display: 'Saira Condensed', sans-serif;
            --font-body: 'Cormorant Garamond', serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        body, .stApp {
            background-color: var(--canvas) !important;
            color: var(--primary) !important;
            font-family: var(--font-body) !important;
        }

        /* Cards */
        div[data-testid="stVerticalBlock"] > div > div[data-testid="stVerticalBlock"] {
            background-color: var(--surface-card) !important;
            border: 1px solid var(--hairline) !important;
            padding: 30px !important;
            border-radius: 12px !important;
        }

        .metric-label {
            font-family: var(--font-mono) !important;
            font-size: 12px !important;
            color: #888888 !important;
            text-transform: uppercase !important;
            letter-spacing: 2px !important;
            margin-bottom: 5px !important;
        }

        .metric-value {
            font-family: var(--font-display) !important;
            font-size: 32px !important;
            color: var(--primary) !important;
        }

        .ev-positive {
            color: var(--success) !important;
            font-weight: bold !important;
        }
        .ev-negative {
            color: var(--error) !important;
            font-weight: bold !important;
        }
        
        .market-badge {
            display: inline-block;
            padding: 5px 15px;
            background-color: #222;
            border: 1px solid #444;
            border-radius: 20px;
            font-family: var(--font-mono);
            font-size: 14px;
            color: #fff;
            margin-bottom: 20px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

load_bugatti_design()

st.title("NFL Top Value Bets")
st.markdown("### Navegue pelas melhores oportunidades da rodada")

@st.cache_data
def load_data():
    try:
        df_bets = pl.read_parquet("data/live_value_bets.parquet").to_pandas()
        df_feats = pl.read_parquet("data/live_features.parquet").select(["player_name", "player_id", "player_display_name"]).unique().to_pandas()
        
        # Load ESPN IDs
        import sys
        sys.path.append("src")
        from nfl_odds.data.collect_nfl import load_player_ids
        df_ids = load_player_ids().select(["gsis_id", "espn_id"]).drop_nulls().to_pandas()
        
        # Merge to get ESPN ID
        df_merged = df_bets.merge(df_feats, on="player_name", how="left")
        df_merged = df_merged.merge(df_ids, left_on="player_id", right_on="gsis_id", how="left")
        
        # Sort by highest EV
        df_merged = df_merged.sort_values(by="ev_percent", ascending=False).reset_index(drop=True)
        return df_merged
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return pd.DataFrame()

df = load_data()

if len(df) == 0:
    st.warning("Nenhuma aposta encontrada ou execute o pipeline primeiro.")
else:
    # Initialize session state for carousel
    if 'card_index' not in st.session_state:
        st.session_state.card_index = 0

    col_nav1, col_nav2, col_nav3 = st.columns([1, 8, 1])
    
    with col_nav1:
        st.write("")
        st.write("")
        st.write("")
        if st.button("⬅️ Anterior", use_container_width=True):
            st.session_state.card_index = max(0, st.session_state.card_index - 1)
            
    with col_nav3:
        st.write("")
        st.write("")
        st.write("")
        if st.button("Próximo ➡️", use_container_width=True):
            st.session_state.card_index = min(len(df) - 1, st.session_state.card_index + 1)
            
    # Get current bet
    idx = st.session_state.card_index
    bet = df.iloc[idx]
    
    # Render Card
    with col_nav2:
        st.markdown(f"<div style='text-align: center; color: #666; font-family: monospace; margin-bottom: 10px;'>Aposta {idx + 1} de {len(df)}</div>", unsafe_allow_html=True)
        
        # Create a visual container
        with st.container():
            col_img, col_info = st.columns([1, 2])
            
            with col_img:
                # Resolve player image
                espn_id = bet.get("espn_id", None)
                if pd.notna(espn_id):
                    img_url = f"https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/{int(espn_id)}.png"
                    st.image(img_url, use_container_width=True)
                else:
                    st.image("https://a.espncdn.com/combiner/i?img=/i/headshots/nophoto.png", use_container_width=True)
                    
            with col_info:
                display_name = bet.get("player_display_name", bet["player_name"])
                if pd.isna(display_name): display_name = bet["player_name"]
                
                st.markdown(f"<h1 style='font-family: var(--font-display); font-size: 48px; margin-bottom: 0px;'>{display_name}</h1>", unsafe_allow_html=True)
                st.markdown(f"<h3 style='color: #888; font-family: var(--font-mono); margin-top: 0px;'>{bet['team']}</h3>", unsafe_allow_html=True)
                
                market_clean = str(bet['market']).replace('_', ' ').upper()
                side_clean = str(bet['side']).upper()
                st.markdown(f"<div class='market-badge'>{market_clean} • {side_clean} {bet['line']}</div>", unsafe_allow_html=True)
                
                # Metrics row
                m1, m2, m3 = st.columns(3)
                
                ev_class = "ev-positive" if bet['ev_percent'] > 0 else "ev-negative"
                ev_sign = "+" if bet['ev_percent'] > 0 else ""
                
                with m1:
                    st.markdown("<div class='metric-label'>EXPECTED VALUE</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='metric-value {ev_class}'>{ev_sign}{bet['ev_percent']:.2f}%</div>", unsafe_allow_html=True)
                with m2:
                    st.markdown("<div class='metric-label'>WIN PROBABILITY</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='metric-value'>{bet['prob_win']*100:.1f}%</div>", unsafe_allow_html=True)
                with m3:
                    st.markdown("<div class='metric-label'>BETCLIC ODDS</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='metric-value'>{bet['odds']:.2f}</div>", unsafe_allow_html=True)
                    
                st.markdown("<br>", unsafe_allow_html=True)
                
                m4, m5, m6 = st.columns(3)
                with m4:
                    st.markdown("<div class='metric-label'>FAIR ODDS (JUSTAS)</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='metric-value' style='font-size: 24px;'>{bet['fair_odds']:.2f}</div>", unsafe_allow_html=True)
                with m5:
                    st.markdown("<div class='metric-label'>MATH EDGE</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='metric-value' style='font-size: 24px;'>{bet['edge']*100:.1f} pp</div>", unsafe_allow_html=True)

import streamlit as st
import pandas as pd
import numpy as np
import warnings
from datetime import datetime
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
import ta
import pytz
from io import BytesIO
from PIL import Image
import matplotlib.pyplot as plt

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Forex Volatility Screener", page_icon="⚡", layout="wide")

st.markdown("""
<style>
    .main > div { padding-top: 2rem; }
    /* Ajustement pour que le header du dataframe ne soit pas en blanc sur fond blanc en thème clair */
    .stDataFrame thead th { background-color: #262730; } 
</style>
""", unsafe_allow_html=True)


# --- Les fonctions (inchangées) ---
try:
    OANDA_ACCESS_TOKEN = st.secrets["OANDA_ACCESS_TOKEN"]
except KeyError:
    st.error("🔑 Secret OANDA_ACCESS_TOKEN non trouvé !")
    st.stop()

INSTRUMENTS_LIST = [
    'EUR_USD', 'USD_JPY', 'GBP_USD', 'USD_CHF', 'AUD_USD', 'USD_CAD', 'NZD_USD',
    'EUR_JPY', 'GBP_JPY', 'CHF_JPY', 'AUD_JPY', 'CAD_JPY', 'NZD_JPY',
    'EUR_GBP', 'EUR_AUD', 'EUR_CAD', 'EUR_CHF', 'EUR_NZD',
    'GBP_AUD', 'GBP_CAD', 'GBP_CHF', 'GBP_NZD', 'XAU_USD'
]
TIMEZONE = 'Europe/Paris'

@st.cache_data(ttl=600, show_spinner=False)
def fetch_multi_timeframe_data(pair, timeframes=['D', 'H4', 'H1']):
    api = API(access_token=OANDA_ACCESS_TOKEN, environment="practice")
    all_data = {}
    for tf in timeframes:
        params = {'granularity': tf, 'count': 100, 'price': 'M'}
        try:
            r = instruments.InstrumentsCandles(instrument=pair, params=params)
            api.request(r)
            candles = r.response.get('candles', [])
            if not candles: continue
            data = [{'Time': c['time'], 'Close': float(c['mid']['c']), 'High': float(c['mid']['h']), 'Low': float(c['mid']['l'])} for c in candles]
            df = pd.DataFrame(data)
            df['Time'] = pd.to_datetime(df['Time']).dt.tz_convert(TIMEZONE)
            all_data[tf] = df
        except: continue
    return all_data if all_data else None

def calculate_volatility_indicators(df):
    if df is None or df.empty or len(df) < 15: return None
    df['atr'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
    adx_indicator = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
    df['adx'] = adx_indicator.adx()
    df['dmi_plus'] = adx_indicator.adx_pos()
    df['dmi_minus'] = adx_indicator.adx_neg()
    return df.dropna()

def get_star_rating(score):
    return "⭐" * int(score) + "☆" * (3 - int(score))

def run_volatility_analysis(instruments_list, params):
    all_results = []
    progress_bar = st.progress(0, text="Initialisation du scan...")
    for i, instrument in enumerate(instruments_list):
        progress_bar.progress((i + 1) / len(instruments_list), text=f"Analyse {instrument} ({i+1}/{len(instruments_list)})")
        multi_tf_data = fetch_multi_timeframe_data(instrument)
        if not multi_tf_data: continue
        data_D = calculate_volatility_indicators(multi_tf_data.get('D'))
        data_H4 = calculate_volatility_indicators(multi_tf_data.get('H4'))
        data_H1 = calculate_volatility_indicators(multi_tf_data.get('H1'))
        if not all([data_D is not None, data_H4 is not None, data_H1 is not None]): continue
        last_D, last_H4, last_H1 = data_D.iloc[-1], data_H4.iloc[-1], data_H1.iloc[-1]
        score = 0
        price = last_H1['Close']
        atr_percent = (last_D['atr'] / price) * 100
        if atr_percent >= params['min_atr_percent']: score += 1
        if last_H4['adx'] > params['min_adx']: score += 1
        if last_H1['adx'] > params['min_adx']: score += 1
        dmi_gap = abs(last_H1['dmi_plus'] - last_H1['dmi_minus'])
        direction = 'Achat' if last_H1['dmi_plus'] > last_H1['dmi_minus'] else 'Vente'
        if last_H1['adx'] < params['min_adx']: direction = 'Range'
        a_plus = atr_percent > 0.8 and last_H4['adx'] > 25 and last_H1['adx'] > 25 and dmi_gap > 5
        label = '💎 A+ Volatility' if a_plus else ''
        all_results.append({'Paire': instrument.replace('_', '/'), 'Tendance H1': direction, 'Prix': price, 'ATR (D) %': atr_percent, 'ADX H1': last_H1['adx'], 'ADX H4': last_H4['adx'], 'Score': score, 'Label': label})
    progress_bar.empty()
    return pd.DataFrame(all_results)

# --- FIN des fonctions ---

# NOUVEAUTÉ : Fonction pour colorer le texte de la tendance
def style_tendance(tendance):
    """Applique une couleur en fonction de la tendance."""
    if tendance == 'Achat':
        return 'color: #2ECC71'  # Vert
    elif tendance == 'Vente':
        return 'color: #E74C3C'  # Rouge
    return 'color: #F1C40F' # Jaune pour "Range"

# --- Début de l'application Streamlit ---
st.markdown('<h1 class="screener-header">⚡ Forex & Gold ADX Screener</h1>', unsafe_allow_html=True)

with st.sidebar:
    st.header("🛠️ Paramètres du Filtre")
    min_score_to_display = st.slider("Note minimale (étoiles)", 0, 3, 1, 1)
    
    # NOUVEAUTÉ : Ajout du filtre de tendance
    tendance_filter = st.radio(
        "Filtrer par Tendance",
        ('Toutes', 'Achat', 'Vente'), horizontal=True
    )
    
    params = {
        'min_atr_percent': st.slider("ATR (Daily) Minimum %", 0.05, 1.50, 0.05, 0.05),
        'min_adx': st.slider("ADX Minimum", 10, 40, 20, 1),
    }

    if st.button("🔄 Rescan"):
        st.session_state.scan_done = False
        st.cache_data.clear()
        st.rerun()

if 'scan_done' not in st.session_state:
    st.session_state.scan_done = False

if not st.session_state.scan_done:
    with st.spinner("Analyse de la volatilité en cours..."):
        st.session_state.results_df = run_volatility_analysis(INSTRUMENTS_LIST, params)
        st.session_state.scan_time = datetime.now()
        st.session_state.scan_done = True
        st.rerun()

if st.session_state.scan_done and 'results_df' in st.session_state:
    df = st.session_state.results_df
    scan_time_str = st.session_state.scan_time.astimezone(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
    st.markdown(f'<div class="update-info">🔄 Scan terminé à {scan_time_str} ({TIMEZONE})</div>', unsafe_allow_html=True)

    if df.empty:
        st.warning("Aucun instrument n'a pu être analysé.")
    else:
        # 1. Filtre par score
        filtered_df = df[df['Score'] >= min_score_to_display]
        
        # 2. NOUVEAUTÉ : Application du filtre de tendance
        if tendance_filter != 'Toutes':
            filtered_df = filtered_df[filtered_df['Tendance H1'] == tendance_filter]

        # 3. Tri final
        filtered_df = filtered_df.sort_values(by='Score', ascending=False)


        if filtered_df.empty:
            st.info(f"Aucune opportunité trouvée avec les filtres actuels.")
        else:
            st.subheader(f"🏆 {len(filtered_df)} Opportunités trouvées")

            filtered_df['Note'] = filtered_df['Score'].apply(get_star_rating)
            display_cols = ['Note', 'Paire', 'Label', 'Tendance H1', 'Prix', 'ATR (D) %', 'ADX H1', 'ADX H4']
            display_df = filtered_df[display_cols]
            
            # NOUVEAUTÉ : Application du style de couleur au dataframe
            st.dataframe(
                display_df.style.applymap(style_tendance, subset=['Tendance H1']),
                column_config={
                    "Prix": st.column_config.NumberColumn("Prix", format="%.4f"),
                    "ATR (D) %": st.column_config.NumberColumn("ATR (D) %", format="%.2f%%"),
                    "ADX H1": st.column_config.NumberColumn("ADX H1", format="%.2f"),
                    "ADX H4": st.column_config.NumberColumn("ADX H4", format="%.2f"),
                },
                use_container_width=True,
                hide_index=True
            )

            # Le code pour le téléchargement d'image reste inchangé
            df_for_image = display_df.copy()
            for col in ['Prix', 'ATR (D) %', 'ADX H1', 'ADX H4']:
                df_for_image[col] = df_for_image[col].apply(lambda x: f"{x:.2f}")
            fig, ax = plt.subplots(figsize=(10, len(df_for_image) * 0.5 + 1))
            ax.axis('tight'); ax.axis('off')
            table = ax.table(cellText=df_for_image.values, colLabels=df_for_image.columns, cellLoc='center', loc='center')
            table.auto_set_font_size(False); table.set_fontsize(10); table.scale(1.2, 1.2)
            buf = BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight', dpi=200)
            buf.seek(0)
            st.download_button("📸 Télécharger les résultats (PNG)", buf, file_name=f'scan_volatilite_{datetime.now().strftime("%Y%m%d_%H%M")}.png', mime="image/png")

with st.expander("ℹ️ Comprendre la Notation (3 Étoiles)"):
    st.markdown("""
    - ⭐ **Volatilité**: L'ATR journalier dépasse le seuil.
    - ⭐ **Tendance Fond**: ADX H4 dépasse le seuil.
    - ⭐ **Tendance Entrée**: ADX H1 dépasse le seuil.
    - 💎 **A+ Volatility**: Tous les indicateurs sont très forts + tendance nette.
    """)
   

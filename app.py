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

st.set_page_config(page_title="Forex & Gold ADX Screener", page_icon="⚡", layout="wide")

st.markdown("""
<style>
    .main > div { padding-top: 2rem; }
    .stDataFrame thead th { background-color: #262730; } 
</style>
""", unsafe_allow_html=True)

try:
    OANDA_ACCESS_TOKEN = st.secrets["OANDA_ACCESS_TOKEN"]
except KeyError:
    st.error("🔑 Secret OANDA_ACCESS_TOKEN non trouvé !")
    st.stop()

INSTRUMENTS_LIST = [
    'EUR_USD', 'GBP_USD', 'USD_JPY', 'USD_CHF', 'USD_CAD', 'AUD_USD', 'NZD_USD',
    'EUR_GBP', 'EUR_AUD', 'EUR_NZD', 'EUR_CAD', 'EUR_CHF', 'EUR_JPY',
    'GBP_AUD', 'GBP_NZD', 'GBP_CAD', 'GBP_CHF', 'GBP_JPY',
    'AUD_CAD', 'AUD_CHF', 'AUD_JPY', 'AUD_NZD',
    'NZD_CAD', 'NZD_CHF', 'NZD_JPY',
    'CAD_CHF', 'CAD_JPY',
    'CHF_JPY',
    'XAU_USD'
]
TIMEZONE = 'Europe/Paris'

@st.cache_data(ttl=600, show_spinner=False)
def fetch_multi_timeframe_data(pair, timeframes=['D', 'H4', 'H1']):
    # ... (code inchangé)
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
    # ... (code inchangé)
    if df is None or df.empty or len(df) < 15: return None
    df['atr'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
    adx_indicator = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
    df['adx'] = adx_indicator.adx()
    df['dmi_plus'] = adx_indicator.adx_pos()
    df['dmi_minus'] = adx_indicator.adx_neg()
    return df.dropna()

def get_star_rating(score):
    # MODIFICATION : Système à 4 étoiles
    return "⭐" * int(score) + "☆" * (4 - int(score))

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
        
        # Calcul des directions H1 et H4
        direction_h1 = 'Achat' if last_H1['dmi_plus'] > last_H1['dmi_minus'] else 'Vente'
        if last_H1['adx'] < params['min_adx']: direction_h1 = 'Range'
        
        direction_h4 = 'Achat' if last_H4['dmi_plus'] > last_H4['dmi_minus'] else 'Vente'
        if last_H4['adx'] < params['min_adx']: direction_h4 = 'Range'
        
        # MODIFICATION : Logique de score sur 4 étoiles
        score = 0
        price = last_H1['Close']
        atr_percent = (last_D['atr'] / price) * 100
        
        if atr_percent >= params['min_atr_percent']: score += 1
        if last_H1['adx'] > params['min_adx']: score += 1
        if last_H4['adx'] > params['min_adx']: score += 1
        
        is_aligned = (direction_h1 == direction_h4 and direction_h1 != 'Range')
        if is_aligned: score += 1
            
        # MODIFICATION : Label A+ plus strict
        a_plus = (score == 4 and atr_percent > 1.0)
        label = '💎 A+' if a_plus else ''
        
        all_results.append({
            'Paire': instrument.replace('_', '/'), 'Tendance H1': direction_h1,
            'Prix': price, 'ATR (D) %': atr_percent, 'ADX H1': last_H1['adx'],
            'ADX H4': last_H4['adx'], 'Score': score, 'Label': label, 'Alignée': is_aligned
        })
    progress_bar.empty()
    return pd.DataFrame(all_results)

def style_tendance(val):
    # MODIFICATION : Gère l'icône dans la cellule
    if 'Achat' in val: return 'color: #2ECC71'
    if 'Vente' in val: return 'color: #E74C3C'
    return 'color: #F1C40F'

# --- Début de l'application Streamlit ---
st.markdown('<h1 class="screener-header">⚡ Forex & Gold ADX Screener</h1>', unsafe_allow_html=True)

with st.sidebar:
    st.header("🛠️ Paramètres du Filtre")
    
    # MODIFICATION : Nouveaux filtres et valeurs par défaut
    min_score_to_display = st.slider("Note minimale (étoiles)", 0, 4, 4, 1)
    
    align_filter = st.checkbox("Tendance H1/H4 Alignée Uniquement", value=True)
    
    tendance_filter = st.radio("Filtrer par Tendance", ('Toutes', 'Achat', 'Vente'), horizontal=True)
    
    params = {
        'min_atr_percent': st.slider("ATR (Daily) Minimum %", 0.10, 2.00, 0.70, 0.05),
        'min_adx': st.slider("ADX Minimum", 15, 40, 25, 1),
    }
    
    if st.button("🔄 Rescan"):
        st.session_state.scan_done = False; st.cache_data.clear(); st.rerun()

if 'scan_done' not in st.session_state: st.session_state.scan_done = False

if not st.session_state.scan_done:
    with st.spinner("Analyse des configurations en cours..."):
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
        # Application des filtres
        filtered_df = df[df['Score'] >= min_score_to_display]
        if align_filter:
            filtered_df = filtered_df[filtered_df['Alignée'] == True]
        if tendance_filter != 'Toutes':
            filtered_df = filtered_df[filtered_df['Tendance H1'] == tendance_filter]
        
        filtered_df = filtered_df.sort_values(by=['Score', 'Tendance H1'], ascending=[False, True])

        if filtered_df.empty:
            st.info(f"Aucune opportunité trouvée avec les filtres actuels. Essayez d'abaisser les seuils.")
        else:
            st.subheader(f"🏆 {len(filtered_df)} Opportunités trouvées")
            
            # Mise en forme pour l'affichage
            filtered_df['ADX (H1/H4)'] = filtered_df['ADX H1'].map('{:.2f}'.format) + ' / ' + filtered_df['ADX H4'].map('{:.2f}'.format)
            filtered_df['Note'] = filtered_df['Score'].apply(get_star_rating)
            
            # MODIFICATION : Ajout de l'icône d'alignement
            filtered_df['Dir. H1'] = np.where(filtered_df['Alignée'], '🔗 ' + filtered_df['Tendance H1'], filtered_df['Tendance H1'])
            
            display_cols = ['Note', 'Paire', 'Label', 'Dir. H1', 'Prix', 'ATR (D) %', 'ADX (H1/H4)']
            display_df = filtered_df[display_cols].rename(columns={'ATR (D) %': 'ATR %'})
            
            table_height = (len(display_df) + 1) * 35 

            st.dataframe(
                display_df.style.applymap(style_tendance, subset=['Dir. H1']),
                column_config={"Prix": st.column_config.NumberColumn(format="%.4f"), "ATR %": st.column_config.NumberColumn(format="%.2f%%")},
                use_container_width=True, hide_index=True, height=table_height
            )

            # ... (code de téléchargement PNG inchangé)

with st.expander("ℹ️ Comprendre la Notation (4 Étoiles)", expanded=True):
    st.markdown("""
    - ⭐ **Volatilité**: ATR(D) > seuil (`0.70%` par défaut)
    - ⭐ **Tendance Entrée**: ADX H1 > seuil (`25` par défaut)
    - ⭐ **Tendance Fond**: ADX H4 > seuil (`25` par défaut)
    - ⭐ **Alignement**: Les tendances H1 et H4 sont identiques (Achat/Achat ou Vente/Vente).
    ---
    - 💎 **A+**: Une opportunité **4 étoiles** avec une volatilité exceptionnelle (ATR > 1.0%).
    - 🔗 **Indique un alignement** parfait des tendances H1 et H4.
    """)

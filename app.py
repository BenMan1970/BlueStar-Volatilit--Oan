# --- START OF FILE app.py (VERSION FINALE) ---

import streamlit as st
import pandas as pd
import numpy as np
import warnings
from datetime import datetime
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
from fpdf import FPDF
import ta
from scipy.signal import find_peaks
import pytz

warnings.filterwarnings('ignore')

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Forex & Gold Screener Pro", page_icon="🎯", layout="wide")

# --- CSS PERSONNALISÉ ---
st.markdown("""
<style>
    .main > div { padding-top: 2rem; }
    .screener-header { font-size: 28px; font-weight: bold; color: #FAFAFA; margin-bottom: 15px; text-align: center; }
    .update-info { background-color: #262730; padding: 8px 15px; border-radius: 5px; margin-bottom: 20px; font-size: 14px; color: #A9A9A9; border: 1px solid #333A49; text-align: center; }
</style>
""", unsafe_allow_html=True)

# --- ACCÈS AUX SECRETS OANDA ---
try:
    OANDA_ACCESS_TOKEN = st.secrets["OANDA_ACCESS_TOKEN"]
except KeyError:
    st.error("🔑 Secret OANDA_ACCESS_TOKEN non trouvé !"); st.stop()

# --- CONSTANTES ---
INSTRUMENTS_LIST = [
    'EUR_USD', 'USD_JPY', 'GBP_USD', 'USD_CHF', 'AUD_USD', 'USD_CAD', 'NZD_USD', 
    'EUR_JPY', 'GBP_JPY', 'CHF_JPY', 'AUD_JPY', 'CAD_JPY', 'NZD_JPY',
    'EUR_GBP', 'EUR_AUD', 'EUR_CAD', 'EUR_CHF', 'EUR_NZD',
    'GBP_AUD', 'GBP_CAD', 'GBP_CHF', 'GBP_NZD',
    'XAU_USD', # On garde l'or
    # On peut rajouter les indices plus tard, une fois que ceci fonctionne
    # 'US30_USD', 'NAS100_USD', 'SPX500_USD' 
]
TIMEZONE = 'Europe/Paris'

# ==============================================================================
# 1. FONCTIONS DE CALCUL ET DE LOGIQUE
# ==============================================================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_multi_timeframe_data(pair, timeframes=['D', 'H4', 'H1']):
    api = API(access_token=OANDA_ACCESS_TOKEN, environment="practice")
    all_data = {}
    for tf in timeframes:
        params = {'granularity': tf, 'count': 100, 'price': 'M'} # 100 bougies suffisent
        try:
            r = instruments.InstrumentsCandles(instrument=pair, params=params)
            api.request(r)
            if 'candles' not in r.response or not r.response['candles']: return None
            data = [{'Time': c['time'], 'Open': float(c['mid']['o']), 'High': float(c['mid']['h']), 'Low': float(c['mid']['l']), 'Close': float(c['mid']['c'])} for c in r.response['candles']]
            df = pd.DataFrame(data)
            df['Time'] = pd.to_datetime(df['Time']).dt.tz_localize('UTC').dt.tz_convert(TIMEZONE)
            all_data[tf] = df
        except Exception:
            return None
    return all_data

def calculate_all_indicators(df):
    # ### CORRECTION : Condition assouplie
    if df is None or len(df) < 55: return None # L'EMA 50 a besoin d'au moins 50 points
    
    df['ema_fast'] = ta.trend.ema_indicator(df['Close'], window=21)
    df['ema_slow'] = ta.trend.ema_indicator(df['Close'], window=50)
    df['atr'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
    adx_indicator = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
    df['adx'] = adx_indicator.adx()
    df['dmi_plus'] = adx_indicator.adx_pos()
    df['dmi_minus'] = adx_indicator.adx_neg()
    df['rsi'] = ta.momentum.rsi(df['Close'], window=14)
    
    # On retourne le DataFrame même avec des NaN, que l'on gèrera plus tard
    return df

def get_star_rating(score):
    return "⭐" * int(score) + "☆" * (5 - int(score))

# ==============================================================================
# 2. LOGIQUE PRINCIPALE D'ANALYSE
# ==============================================================================
def run_full_analysis(instruments_list, params):
    all_results = []
    progress_bar = st.progress(0, text="Initialisation du scan...")
    
    for i, instrument in enumerate(instruments_list):
        progress_text = f"Analyse de {instrument.replace('_', '/')}... ({i+1}/{len(instruments_list)})"
        progress_bar.progress((i + 1) / len(instruments_list), text=progress_text)
        
        multi_tf_data = fetch_multi_timeframe_data(instrument)
        if multi_tf_data is None: continue

        data_D = calculate_all_indicators(multi_tf_data.get('D'))
        data_H4 = calculate_all_indicators(multi_tf_data.get('H4'))
        data_H1 = calculate_all_indicators(multi_tf_data.get('H1'))
        
        # ### CORRECTION : On vérifie que les dernières données existent après calcul
        if data_D is None or data_H4 is None or data_H1 is None or data_D.empty or data_H4.empty or data_H1.empty:
            continue
            
        last_D, last_H4, last_H1 = data_D.iloc[-1], data_H4.iloc[-1], data_H1.iloc[-1]

        # ### CORRECTION : Vérifier que les indicateurs ne sont pas NaN
        required_cols = ['atr', 'adx', 'dmi_plus', 'dmi_minus', 'rsi', 'ema_fast', 'ema_slow']
        if last_D[required_cols].isnull().any() or last_H4[required_cols].isnull().any() or last_H1[required_cols].isnull().any():
            continue

        price = last_H1['Close']
        score = 0
        
        atr_percent = (last_D['atr'] / price) * 100
        if atr_percent >= params['min_atr_percent']: score += 1

        trend_H4 = 'Bullish' if last_H4['ema_fast'] > last_H4['ema_slow'] else 'Bearish'
        trend_H1 = 'Bullish' if last_H1['ema_fast'] > last_H1['ema_slow'] else 'Bearish'
        
        if last_H4['adx'] > params['min_adx'] and ((trend_H4 == 'Bullish' and last_H4['dmi_plus'] > last_H4['dmi_minus']) or (trend_H4 == 'Bearish' and last_H4['dmi_minus'] > last_H4['dmi_plus'])): score += 1
        if last_H1['adx'] > params['min_adx'] and ((trend_H1 == 'Bullish' and last_H1['dmi_plus'] > last_H1['dmi_minus']) or (trend_H1 == 'Bearish' and last_H1['dmi_minus'] > last_H1['dmi_plus'])): score += 1
        if trend_H1 == trend_H4: score += 1
        if params['rsi_min'] < last_H1['rsi'] < params['rsi_max']: score += 1

        all_results.append({
            'Paire': instrument.replace('_', '/'), 'Direction': trend_H1, 'Prix': price,
            'ATR (D) %': atr_percent, 'ADX H1': last_H1['adx'], 'ADX H4': last_H4['adx'],
            'RSI H1': last_H1['rsi'], 'Score': score
        })
        
    progress_bar.empty()
    return pd.DataFrame(all_results)

# ==============================================================================
# 3. FONCTION D'EXPORT PDF (simplifiée pour le test)
# ==============================================================================
def create_pdf_report(df):
    pdf = FPDF(orientation='L', unit='mm', format='A4'); pdf.add_page()
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Rapport Screener', 0, 1, 'C')
    # ...
    return bytes(pdf.output())

# ==============================================================================
# 4. INTERFACE UTILISATEUR
# ==============================================================================
st.markdown('<h1 class="screener-header">🎯 Forex & Gold Screener Pro</h1>', unsafe_allow_html=True)
with st.sidebar:
    st.header("🛠️ Paramètres du Filtre")
    min_score_to_display = st.slider("Note minimale (étoiles)", 0, 5, 1, 1) # Par défaut à 1 étoile
    params = {
        'min_atr_percent': st.slider("ATR (Daily) Minimum %", 0.1, 2.0, 0.4, 0.05),
        'min_adx': st.slider("ADX Minimum (H1 & H4)", 15, 30, 20, 1),
        'rsi_min': st.slider("RSI H1 Minimum", 10, 40, 30, 1),
        'rsi_max': st.slider("RSI H1 Maximum", 60, 90, 70, 1),
    }

if 'scan_done' not in st.session_state: st.session_state.scan_done = False
col1, col2, _ = st.columns([1.5, 1.5, 5])
with col1:
    if st.button("🔎 Lancer / Rescan", use_container_width=True, type="primary"):
        st.session_state.scan_done = False; st.cache_data.clear(); st.rerun()

if not st.session_state.scan_done:
    with st.spinner("Analyse en cours..."):
        st.session_state.results_df = run_full_analysis(INSTRUMENTS_LIST, params)
        st.session_state.scan_time = datetime.now(); st.session_state.scan_done = True; st.rerun()

if st.session_state.scan_done and 'results_df' in st.session_state:
    df = st.session_state.results_df
    scan_time_str = st.session_state.scan_time.astimezone(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
    st.markdown(f'<div class="update-info">🔄 Scan terminé à {scan_time_str} ({TIMEZONE})</div>', unsafe_allow_html=True)
    
    if df.empty:
        st.warning("Aucun instrument n'a pu être complètement analysé. Les conditions du marché sont peut-être inhabituelles ou les données sont incomplètes.")
    else:
        filtered_df = df[df['Score'] >= min_score_to_display].sort_values(by='Score', ascending=False)
        if filtered_df.empty:
            st.info(f"Aucune opportunité trouvée avec une note d'au moins {min_score_to_display} étoile(s). Essayez de baisser la note minimale.")
        else:
            st.subheader(f"🏆 {len(filtered_df)} Opportunités trouvées")
            with col2:
                pdf_data = create_pdf_report(filtered_df)
                st.download_button(label="📄 Exporter en PDF", data=pdf_data, file_name=f"Screener_Report.pdf", mime="application/pdf", use_container_width=True)
            
            filtered_df['Note'] = filtered_df['Score'].apply(get_star_rating)
            display_df = filtered_df.copy()
            cols_to_format = ['Prix', 'ATR (D) %', 'ADX H1', 'ADX H4', 'RSI H1']
            for col in cols_to_format:
                display_df[col] = display_df[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "N/A")
            
            display_cols = ['Note', 'Direction', 'Prix', 'ATR (D) %', 'ADX H1', 'ADX H4', 'RSI H1']
            def style_dataframe(df_to_style):
                def style_direction(direction):
                    color = 'lightgreen' if direction == 'Bullish' else 'lightcoral'
                    return f'color: {color}; font-weight: bold;'
                return df_to_style.style.applymap(style_direction, subset=['Direction'])
            
            st.dataframe(style_dataframe(display_df.set_index('Paire')[display_cols]), use_container_width=True)

with st.expander("ℹ️ Comprendre la Stratégie et la Notation"):
    st.markdown("""...""")

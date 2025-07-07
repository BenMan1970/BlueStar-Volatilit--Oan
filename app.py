# --- START OF FILE app.py ---

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
st.set_page_config(
    page_title="Forex & Gold Screener Pro",
    page_icon="🎯",
    layout="wide"
)

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
    st.error("🔑 Secret OANDA_ACCESS_TOKEN non trouvé ! Veuillez le configurer.")
    st.stop()

# --- CONSTANTES ---
# ### CORRECTION : Liste simplifiée pour le test
INSTRUMENTS_LIST = [
    # Majors Forex
    'EUR_USD', 'USD_JPY', 'GBP_USD', 'USD_CHF', 'AUD_USD', 'USD_CAD', 'NZD_USD', 
    # Crosses Forex
    'EUR_JPY', 'GBP_JPY', 'CHF_JPY', 'AUD_JPY', 'CAD_JPY', 'NZD_JPY',
    'EUR_GBP', 'EUR_AUD', 'EUR_CAD', 'EUR_CHF', 'EUR_NZD',
    'GBP_AUD', 'GBP_CAD', 'GBP_CHF', 'GBP_NZD',
    # Métaux
    'XAU_USD' # Or
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
        params = {'granularity': tf, 'count': 200, 'price': 'M'}
        try:
            r = instruments.InstrumentsCandles(instrument=pair, params=params)
            api.request(r)
            if 'candles' not in r.response or not r.response['candles']:
                return None 

            data = [{'Time': c['time'], 'Open': float(c['mid']['o']), 'High': float(c['mid']['h']), 'Low': float(c['mid']['l']), 'Close': float(c['mid']['c'])} for c in r.response['candles']]
            df = pd.DataFrame(data)
            df['Time'] = pd.to_datetime(df['Time']).dt.tz_localize('UTC').dt.tz_convert(TIMEZONE)
            all_data[tf] = df
        except Exception:
            return None
    return all_data

def calculate_all_indicators(df):
    if df is None or len(df) < 50: return None
    df['ema_fast'] = ta.trend.ema_indicator(df['Close'], window=21)
    df['ema_slow'] = ta.trend.ema_indicator(df['Close'], window=50)
    df['atr'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
    adx_indicator = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
    df['adx'] = adx_indicator.adx()
    df['dmi_plus'] = adx_indicator.adx_pos()
    df['dmi_minus'] = adx_indicator.adx_neg()
    df['rsi'] = ta.momentum.rsi(df['Close'], window=14)
    return df.dropna()

def get_star_rating(score):
    return "⭐" * int(score) + "☆" * (5 - int(score))

# ==============================================================================
# 2. LOGIQUE PRINCIPALE D'ANALYSE
# ==============================================================================
def run_full_analysis(instruments_list, params):
    all_results = []
    failed_instruments = []
    
    progress_bar = st.progress(0, text="Initialisation du scan...")
    
    for i, instrument in enumerate(instruments_list):
        progress_text = f"Analyse de {instrument.replace('_', '/')}... ({i+1}/{len(instruments_list)})"
        progress_bar.progress((i + 1) / len(instruments_list), text=progress_text)
        
        multi_tf_data = fetch_multi_timeframe_data(instrument)
        if multi_tf_data is None:
            failed_instruments.append(instrument)
            continue

        data_D = calculate_all_indicators(multi_tf_data['D'])
        data_H4 = calculate_all_indicators(multi_tf_data['H4'])
        data_H1 = calculate_all_indicators(multi_tf_data['H1'])
        if data_D is None or data_H4 is None or data_H1 is None: continue
            
        last_D, last_H4, last_H1 = data_D.iloc[-1], data_H4.iloc[-1], data_H1.iloc[-1]
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
    if failed_instruments:
        st.toast(f"Échec de récupération pour : {', '.join(failed_instruments)}", icon="⚠️")
        
    return pd.DataFrame(all_results)

# ==============================================================================
# 3. FONCTION D'EXPORT PDF
# ==============================================================================
def create_pdf_report(df, params, scan_time):
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 15); self.cell(0, 10, 'Rapport - Screener Intraday Pro', 0, 1, 'C'); self.set_font('Arial', '', 9)
            self.cell(0, 5, f'Scan du {scan_time}', 0, 1, 'C'); self.ln(2)
        def footer(self): self.set_y(-15); self.set_font('Arial', 'I', 8); self.cell(0, 10, 'Page ' + str(self.page_no()), 0, 0, 'C')
    pdf = PDF(orientation='L', unit='mm', format='A4'); pdf.add_page()
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Rapport des opportunites', 0, 1, 'L')
    if not df.empty:
        df_copy = df.copy()
        df_copy['Note'] = df_copy['Score'].apply(get_star_rating)
        for index, row in df_copy.iterrows():
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 8, f"{row['Paire']} - {row['Note']} - {row['Direction']}", 0, 1)
    return bytes(pdf.output())

# ==============================================================================
# 4. INTERFACE UTILISATEUR
# ==============================================================================
st.markdown('<h1 class="screener-header">🎯 Forex & Gold Screener Pro</h1>', unsafe_allow_html=True)
with st.sidebar:
    st.header("🛠️ Paramètres du Filtre")
    min_score_to_display = st.slider("Note minimale (étoiles)", 0, 5, 3, 1, help="Affiche les opportunités avec au moins cette note.")
    params = {
        'min_atr_percent': st.slider("ATR (Daily) Minimum %", 0.1, 2.0, 0.5, 0.05),
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
        st.error("Aucune donnée n'a pu être récupérée. Cela peut être dû à un problème de connexion avec l'API OANDA ou à un problème avec votre clé d'accès.")
    else:
        filtered_df = df[df['Score'] >= min_score_to_display].sort_values(by='Score', ascending=False)
        if filtered_df.empty:
            st.info(f"Aucune opportunité trouvée avec une note d'au moins {min_score_to_display} étoile(s). Essayez de baisser la note minimale.")
        else:
            st.subheader(f"🏆 {len(filtered_df)} Opportunités trouvées")
            with col2:
                pdf_data = create_pdf_report(filtered_df, params, scan_time_str)
                st.download_button(label="📄 Exporter en PDF", data=pdf_data, file_name=f"Screener_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf", mime="application/pdf", use_container_width=True)
            
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
    st.markdown("""
    Cette application note les opportunités sur 5 étoiles :
    - ⭐ **Volatilité**: ATR(D) > seuil.
    - ⭐ **Tendance H4**: ADX > seuil ET DMI aligné.
    - ⭐ **Tendance H1**: ADX > seuil ET DMI aligné.
    - ⭐ **Confluence**: La tendance H1 est la même que la tendance H4.
    - ⭐ **Momentum**: RSI H1 dans la zone de confort (ni sur-vendu, ni sur-acheté).
    """)
# --- END OF FILE app.py ---

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
    page_title="Forex & Indices Screener Pro",
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
# MISE À JOUR : Liste complète incluant Forex, Or et Indices
INSTRUMENTS_LIST = [
    # Majors Forex
    'EUR_USD', 'USD_JPY', 'GBP_USD', 'USD_CHF', 'AUD_USD', 'USD_CAD', 'NZD_USD', 
    # Crosses Forex
    'EUR_JPY', 'GBP_JPY', 'CHF_JPY', 'AUD_JPY', 'CAD_JPY', 'NZD_JPY',
    'EUR_GBP', 'EUR_AUD', 'EUR_CAD', 'EUR_CHF', 'EUR_NZD',
    'GBP_AUD', 'GBP_CAD', 'GBP_CHF', 'GBP_NZD',
    # Métaux
    'XAU_USD', # Or
    # Indices
    'US30_USD',  # Dow Jones
    'NAS100_USD',# Nasdaq 100
    'SPX500_USD' # S&P 500
]
TIMEZONE = 'Europe/Paris'

# ==============================================================================
# 1. FONCTIONS DE RÉCUPÉRATION ET DE CALCUL
# ==============================================================================

@st.cache_data(ttl=600, show_spinner="Fetching OANDA data...")
def fetch_multi_timeframe_data(pair, timeframes=['D', 'H4', 'H1']):
    api = API(access_token=OANDA_ACCESS_TOKEN, environment="practice")
    all_data = {}
    for tf in timeframes:
        params = {'granularity': tf, 'count': 200, 'price': 'M'}
        try:
            r = instruments.InstrumentsCandles(instrument=pair, params=params)
            api.request(r)
            data = [{'Time': c['time'], 'Open': float(c['mid']['o']), 'High': float(c['mid']['h']), 
                     'Low': float(c['mid']['l']), 'Close': float(c['mid']['c'])} 
                    for c in r.response['candles']]
            if not data: continue
            df = pd.DataFrame(data)
            df['Time'] = pd.to_datetime(df['Time']).dt.tz_localize('UTC').dt.tz_convert(TIMEZONE)
            all_data[tf] = df
        except Exception:
            continue
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

def determine_trend(df_row):
    if df_row['ema_fast'] > df_row['ema_slow']: return 'Bullish'
    elif df_row['ema_fast'] < df_row['ema_slow']: return 'Bearish'
    return 'Neutral'

def find_sr_levels(df, lookback=60):
    recent_df = df.tail(lookback)
    price = recent_df['Close'].iloc[-1]
    res_idx, _ = find_peaks(recent_df['High'], distance=5, prominence=recent_df['atr'].mean() * 0.5)
    sup_idx, _ = find_peaks(-recent_df['Low'], distance=5, prominence=recent_df['atr'].mean() * 0.5)
    resistances = recent_df['High'].iloc[res_idx]
    supports = recent_df['Low'].iloc[sup_idx]
    next_res = resistances[resistances > price].min() if not resistances[resistances > price].empty else np.nan
    next_sup = supports[supports < price].max() if not supports[supports < price].empty else np.nan
    return next_sup, next_res

# ==============================================================================
# 2. LOGIQUE PRINCIPALE D'ANALYSE ET DE FILTRAGE
# ==============================================================================

def run_full_analysis(instruments_list, params):
    filtered_pairs = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, instrument in enumerate(instruments_list):
        status_text.text(f"Analyse de {instrument.replace('_', '/')}... ({i+1}/{len(instruments_list)})")
        multi_tf_data = fetch_multi_timeframe_data(instrument, timeframes=['D', 'H4', 'H1'])
        if not all(tf in multi_tf_data for tf in ['D', 'H4', 'H1']): continue

        data_D = calculate_all_indicators(multi_tf_data['D'])
        data_H4 = calculate_all_indicators(multi_tf_data['H4'])
        data_H1 = calculate_all_indicators(multi_tf_data['H1'])

        if data_D is None or data_H4 is None or data_H1 is None: continue
            
        last_D, last_H4, last_H1 = data_D.iloc[-1], data_H4.iloc[-1], data_H1.iloc[-1]
        price = last_H1['Close']
        score = 0
        
        atr_percent = (last_D['atr'] / price) * 100
        if atr_percent < params['min_atr_percent']: continue
        score += 25

        trend_H4, trend_H1 = determine_trend(last_H4), determine_trend(last_H1)
        if not (last_H4['adx'] > params['min_adx'] and last_H1['adx'] > params['min_adx']): continue
        score += 25

        if trend_H1 != trend_H4 or trend_H1 == 'Neutral': continue
        score += 25
        
        direction = ""
        if trend_H1 == 'Bullish' and last_H1['dmi_plus'] > last_H1['dmi_minus'] and last_H4['dmi_plus'] > last_H4['dmi_minus']:
            direction = 'Achat'
        elif trend_H1 == 'Bearish' and last_H1['dmi_minus'] > last_H1['dmi_plus'] and last_H4['dmi_minus'] > last_H4['dmi_plus']:
            direction = 'Vente'
        else: continue

        if not (params['rsi_min'] < last_H1['rsi'] < params['rsi_max']): continue
        score += 25
        
        sup, res = find_sr_levels(multi_tf_data['H1'])

        filtered_pairs.append({
            'Paire': instrument.replace('_', '/'), 'Direction': direction, 'Prix': price,
            'ATR (D) %': atr_percent, 'ADX H1': last_H1['adx'], 'ADX H4': last_H4['adx'],
            'RSI H1': last_H1['rsi'], 'Prochain Supp': sup, 'Prochaine Rés': res, 'Score': score
        })
        progress_bar.progress((i + 1) / len(instruments_list))

    status_text.empty()
    progress_bar.empty()
    return pd.DataFrame(filtered_pairs)

# ==============================================================================
# 3. FONCTION D'EXPORT PDF
# ==============================================================================

def create_pdf_report(df, params, scan_time):
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 15)
            self.cell(0, 10, 'Rapport - Screener Intraday Pro', 0, 1, 'C')
            self.set_font('Arial', '', 9)
            self.cell(0, 5, f'Scan du {scan_time}', 0, 1, 'C')
            self.ln(2)
            param_str = f"Paramètres: ATR > {params['min_atr_percent']}% | ADX > {params['min_adx']} | RSI entre {params['rsi_min']}-{params['rsi_max']}"
            self.cell(0, 5, param_str, 0, 1, 'C')
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, 'Page ' + str(self.page_no()), 0, 0, 'C')

    pdf = PDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    pdf.set_font('Arial', 'B', 8)
    pdf.set_fill_color(230, 230, 230)
    
    col_widths = {'Paire': 25, 'Direction': 20, 'Prix': 25, 'ATR (D) %': 20, 'ADX H1': 20, 'ADX H4': 20, 'RSI H1': 20, 'Prochain Supp': 30, 'Prochaine Rés': 30, 'Score': 15}
    for col_name, width in col_widths.items():
        pdf.cell(width, 8, col_name, 1, 0, 'C', True)
    pdf.ln()

    pdf.set_font('Arial', '', 8)
    for _, row in df.iterrows():
        is_buy = row['Direction'] == 'Achat'
        if is_buy: pdf.set_text_color(0, 100, 0)
        else: pdf.set_text_color(180, 0, 0)

        pdf.cell(col_widths['Paire'], 8, row['Paire'], 1, 0, 'C')
        pdf.cell(col_widths['Direction'], 8, row['Direction'], 1, 0, 'C')
        
        pdf.set_text_color(0, 0, 0)
        pdf.cell(col_widths['Prix'], 8, f"{row['Prix']:.4f}", 1, 0, 'C')
        pdf.cell(col_widths['ATR (D) %'], 8, f"{row['ATR (D) %']:.2f}%", 1, 0, 'C')
        pdf.cell(col_widths['ADX H1'], 8, f"{row['ADX H1']:.2f}", 1, 0, 'C')
        pdf.cell(col_widths['ADX H4'], 8, f"{row['ADX H4']:.2f}", 1, 0, 'C')
        pdf.cell(col_widths['RSI H1'], 8, f"{row['RSI H1']:.2f}", 1, 0, 'C')
        pdf.cell(col_widths['Prochain Supp'], 8, f"{row['Prochain Supp']:.4f}" if pd.notna(row['Prochain Supp']) else "N/A", 1, 0, 'C')
        pdf.cell(col_widths['Prochaine Rés'], 8, f"{row['Prochaine Rés']:.4f}" if pd.notna(row['Prochaine Rés']) else "N/A", 1, 0, 'C')
        pdf.cell(col_widths['Score'], 8, str(row['Score']), 1, 0, 'C')
        pdf.ln()

    return bytes(pdf.output())

# ==============================================================================
# 4. INTERFACE UTILISATEUR (STREAMLIT)
# ==============================================================================

st.markdown('<h1 class="screener-header">🎯 Forex & Indices Screener Pro</h1>', unsafe_allow_html=True)

with st.sidebar:
    st.header("🛠️ Paramètres du Filtre")
    params = {
        'min_atr_percent': st.slider("ATR (Daily) Minimum %", 0.1, 2.0, 0.5, 0.05, help="Volatilité minimale requise."),
        'min_adx': st.slider("ADX Minimum (H1 & H4)", 15, 30, 20, 1, help="Force de tendance minimale."),
        'rsi_min': st.slider("RSI H1 Minimum", 10, 40, 30, 1),
        'rsi_max': st.slider("RSI H1 Maximum", 60, 90, 70, 1),
    }

if 'scan_done' not in st.session_state: st.session_state.scan_done = False

col1, col2, _ = st.columns([1.5, 1.5, 5])
with col1:
    if st.button("🔎 Lancer / Rescan", use_container_width=True, type="primary"):
        st.session_state.scan_done = False
        st.cache_data.clear()
        st.rerun()

if not st.session_state.scan_done:
    with st.spinner("Analyse en cours..."):
        st.session_state.results_df = run_full_analysis(INSTRUMENTS_LIST, params)
        st.session_state.scan_time = datetime.now()
        st.session_state.scan_done = True
        st.rerun()

if st.session_state.scan_done and 'results_df' in st.session_state:
    df = st.session_state.results_df
    scan_time_str = st.session_state.scan_time.astimezone(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")

    st.markdown(f'<div class="update-info">🔄 Scan terminé à {scan_time_str} ({TIMEZONE})</div>', unsafe_allow_html=True)
    
    if df.empty:
        st.info("Aucune opportunité trouvée avec les paramètres actuels. Essayez de les assouplir.")
    else:
        st.subheader(f"🏆 {len(df)} Opportunités trouvées")
        
        with col2:
            pdf_data = create_pdf_report(df, params, scan_time_str)
            st.download_button(
                label="📄 Exporter en PDF",
                data=pdf_data,
                file_name=f"Screener_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        
        display_df = df.copy()
        for col in ['Prix', 'ATR (D) %', 'ADX H1', 'ADX H4', 'RSI H1', 'Prochain Supp', 'Prochaine Rés']:
            display_df[col] = display_df[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "N/A")
        
        def style_dataframe(df_to_style):
            def style_direction(direction):
                color = 'lightgreen' if direction == 'Achat' else 'lightcoral'
                return f'color: {color}; font-weight: bold;'
            return df_to_style.style.applymap(style_direction, subset=['Direction'])
        
        st.dataframe(style_dataframe(display_df.set_index('Paire')), use_container_width=True)

with st.expander("ℹ️ Comprendre la Stratégie et les Colonnes"):
    st.markdown("""(Votre guide utilisateur ici...)""")

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
    .screener-header { font-size: 28px; font-weight: bold; color: #FAFAFA; margin-bottom: 15px; text-align: center; }
    .update-info { background-color: #262730; padding: 8px 15px; border-radius: 5px; margin-bottom: 20px; font-size: 14px; color: #A9A9A9; border: 1px solid #333A49; text-align: center; }
</style>
""", unsafe_allow_html=True)

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
            if not candles:
                continue
            data = [{'Time': c['time'], 'Close': float(c['mid']['c']), 'High': float(c['mid']['h']), 'Low': float(c['mid']['l'])} for c in candles]
            df = pd.DataFrame(data)
            df['Time'] = pd.to_datetime(df['Time']).dt.tz_convert(TIMEZONE)
            all_data[tf] = df
        except:
            continue
    return all_data if all_data else None


def calculate_volatility_indicators(df):
    if df is None or df.empty or len(df) < 15:
        return None
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
        if not multi_tf_data:
            continue

        data_D = calculate_volatility_indicators(multi_tf_data.get('D'))
        data_H4 = calculate_volatility_indicators(multi_tf_data.get('H4'))
        data_H1 = calculate_volatility_indicators(multi_tf_data.get('H1'))

        if not all([data_D is not None, data_H4 is not None, data_H1 is not None]):
            continue

        last_D, last_H4, last_H1 = data_D.iloc[-1], data_H4.iloc[-1], data_H1.iloc[-1]

        score = 0
        price = last_H1['Close']
        atr_percent = (last_D['atr'] / price) * 100
        if atr_percent >= params['min_atr_percent']: score += 1
        if last_H4['adx'] > params['min_adx']: score += 1
        if last_H1['adx'] > params['min_adx']: score += 1

        dmi_gap = abs(last_H1['dmi_plus'] - last_H1['dmi_minus'])
        direction = 'Achat' if last_H1['dmi_plus'] > last_H1['dmi_minus'] else 'Vente' if last_H1['adx'] > params['min_adx'] else 'Range'

        a_plus = atr_percent > 0.8 and last_H4['adx'] > 25 and last_H1['adx'] > 25 and dmi_gap > 5
        label = '💎 A+ Volatility' if a_plus else ''

        all_results.append({
            'Paire': instrument.replace('_', '/'), 'Tendance H1': direction, 'Prix': price,
            'ATR (D) %': atr_percent, 'ADX H1': last_H1['adx'], 'ADX H4': last_H4['adx'],
            'Score': score, 'Label': label
        })

    progress_bar.empty()
    return pd.DataFrame(all_results)


st.markdown('<h1 class="screener-header">⚡ Forex & Gold ADX Screener</h1>', unsafe_allow_html=True)

with st.sidebar:
    st.header("🛠️ Paramètres du Filtre")
    min_score_to_display = st.slider("Note minimale (étoiles)", 0, 3, 0, 1)
    params = {
        'min_atr_percent': st.slider("ATR (Daily) Minimum %", 0.05, 1.50, 0.05, 0.05),
        'min_adx': st.slider("ADX Minimum", 10, 40, 10, 1),
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
        st.warning("Aucun instrument ne correspond aux critères.")
    else:
        filtered_df = df[df['Score'] >= min_score_to_display].sort_values(by='Score', ascending=False)

        if filtered_df.empty:
            st.info(f"Aucune opportunité trouvée.")
        else:
            st.subheader(f"🏆 {len(filtered_df)} Opportunités trouvées")

            filtered_df['Note'] = filtered_df['Score'].apply(get_star_rating)
            display_df = filtered_df.copy()
            cols_to_format = ['Prix', 'ATR (D) %', 'ADX H1', 'ADX H4']
            for col in cols_to_format:
                display_df[col] = display_df[col].apply(lambda x: f"{x:.2f}")

            display_cols = ['Note', 'Label', 'Tendance H1', 'Prix', 'ATR (D) %', 'ADX H1', 'ADX H4']

            fig, ax = plt.subplots(figsize=(10, len(display_df) * 0.5 + 1))
            ax.axis('tight')
            ax.axis('off')
            table = ax.table(cellText=display_df[display_cols].values,
                             colLabels=display_df[display_cols].columns,
                             cellLoc='center', loc='center')

            buf = BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight', dpi=200)
            buf.seek(0)

            st.image(buf, caption='Résultats du Scan')
            st.download_button("📸 Télécharger l'image PNG", buf, file_name='scan_volatilite.png', mime="image/png")

with st.expander("ℹ️ Comprendre la Notation (3 Étoiles)"):
    st.markdown("""
    - ⭐ **Volatilité**: L'ATR journalier dépasse le seuil.
    - ⭐ **Tendance Fond**: ADX H4 dépasse le seuil.
    - ⭐ **Tendance Entrée**: ADX H1 dépasse le seuil.
    - 💎 **A+ Volatility**: Tous les indicateurs sont très forts + tendance nette.
    """)

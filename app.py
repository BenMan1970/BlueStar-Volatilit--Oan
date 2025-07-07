# --- START OF FILE app.py (VERSION AUTOPSIE) ---

import streamlit as st
import pandas as pd
import numpy as np
import warnings
from datetime import datetime
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
import ta
import pytz

warnings.filterwarnings('ignore')

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Screener Autopsy", page_icon="🔬", layout="wide")

# --- ACCÈS AUX SECRETS OANDA ---
try:
    OANDA_ACCESS_TOKEN = st.secrets["OANDA_ACCESS_TOKEN"]
except KeyError:
    st.error("🔑 Secret OANDA_ACCESS_TOKEN non trouvé !"); st.stop()

# --- CONSTANTES ---
INSTRUMENTS_LIST = ['EUR_USD', 'GBP_USD', 'USD_JPY', 'XAU_USD'] # Liste minimale pour un test rapide
TIMEZONE = 'Europe/Paris'

# --- FONCTIONS DE CALCUL (INCHANGÉES) ---
@st.cache_data(ttl=10, show_spinner=False) 
def fetch_multi_timeframe_data(pair, timeframes=['D', 'H4', 'H1']):
    api = API(access_token=OANDA_ACCESS_TOKEN, environment="practice")
    all_data = {}
    for tf in timeframes:
        params = {'granularity': tf, 'count': 50, 'price': 'M'}
        try:
            r = instruments.InstrumentsCandles(instrument=pair, params=params)
            api.request(r)
            if 'candles' not in r.response or not r.response['candles']: return None
            data = [{'Time': c['time'], 'Close': float(c['mid']['c']), 'High': float(c['mid']['h']), 'Low': float(c['mid']['l'])} for c in r.response['candles']]
            df = pd.DataFrame(data)
            df['Time'] = pd.to_datetime(df['Time']).dt.tz_localize('UTC').dt.tz_convert(TIMEZONE)
            all_data[tf] = df
        except Exception:
            return None
    return all_data

def calculate_volatility_indicators(df):
    if df is None or len(df) < 30: return None
    df['atr'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
    adx_indicator = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
    df['adx'] = adx_indicator.adx()
    df['dmi_plus'] = adx_indicator.adx_pos()
    df['dmi_minus'] = adx_indicator.adx_neg()
    # IMPORTANT: On supprime les lignes initiales qui contiennent des NaN
    return df.dropna().reset_index(drop=True)

# ==============================================================================
# 2. LOGIQUE D'AUTOPSIE
# ==============================================================================
def run_autopsy(instruments_list):
    autopsy_reports = []
    progress_bar = st.progress(0, text="Lancement de l'autopsie des données...")
    
    for i, instrument in enumerate(instruments_list):
        progress_text = f"Analyse de {instrument.replace('_', '/')}... ({i+1}/{len(instruments_list)})"
        progress_bar.progress((i + 1) / len(instruments_list), text=progress_text)
        
        multi_tf_data = fetch_multi_timeframe_data(instrument)
        if multi_tf_data is None: 
            autopsy_reports.append({'Instrument': instrument, 'Statut': 'Échec Récupération Données'})
            continue

        data_H1 = calculate_volatility_indicators(multi_tf_data.get('H1'))
        
        if data_H1 is None or data_H1.empty:
            autopsy_reports.append({'Instrument': instrument, 'Statut': 'Échec Calcul Indicateurs H1'})
            continue
        
        # On prend la dernière ligne complète
        last_row_data = data_H1.iloc[-1].to_dict()
        last_row_data['Instrument'] = instrument
        last_row_data['Statut'] = 'OK'
        
        autopsy_reports.append(last_row_data)
        
    progress_bar.empty()
    return pd.DataFrame(autopsy_reports)

# ==============================================================================
# 3. INTERFACE UTILISATEUR DE DÉBOGAGE
# ==============================================================================
st.markdown('<h1 style="text-align: center;">🔬 Autopsie des Données OANDA</h1>', unsafe_allow_html=True)
st.warning("Cet outil ne filtre rien. Il affiche les données brutes de la dernière bougie H1 pour chaque instrument après le calcul des indicateurs. L'objectif est de vérifier si les valeurs (ATR, ADX...) sont correctement calculées ou si elles sont nulles (NaN).")

if st.button("🔬 Lancer l'autopsie", use_container_width=True, type="primary"):
    with st.spinner("Analyse en cours..."):
        st.session_state.autopsy_df = run_autopsy(INSTRUMENTS_LIST)
        st.session_state.autopsy_done = True

if 'autopsy_done' in st.session_state and st.session_state.autopsy_done:
    st.subheader("Rapport d'autopsie :")
    
    df = st.session_state.autopsy_df
    
    if df.empty:
        st.error("Échec total. Même l'outil d'autopsie n'a rien pu analyser. Le problème est très probablement lié à la clé API ou à une indisponibilité majeure du service OANDA.")
    else:
        # On réorganise les colonnes pour une meilleure lisibilité
        cols = ['Instrument', 'Statut', 'Time', 'Close', 'atr', 'adx', 'dmi_plus', 'dmi_minus']
        display_cols = [col for col in cols if col in df.columns]
        
        st.dataframe(df[display_cols].set_index('Instrument'), use_container_width=True)

        # Analyse automatique des résultats
        if 'adx' in df.columns and df['adx'].isnull().all():
            st.error("Problème détecté : La colonne 'adx' ne contient que des valeurs nulles (NaN). Le calcul de l'ADX échoue systématiquement.")
        elif 'atr' in df.columns and df['atr'].isnull().all():
             st.error("Problème détecté : La colonne 'atr' ne contient que des valeurs nulles (NaN). Le calcul de l'ATR échoue systématiquement.")
        else:
            st.success("Les données semblent être calculées. Si aucune opportunité n'apparaît dans la version normale, le problème vient des seuils de filtrage qui sont trop stricts pour les conditions de marché actuelles.")

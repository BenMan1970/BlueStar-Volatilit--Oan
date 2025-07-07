# --- START OF FILE app.py (VERSION DE DÉBOGAGE) ---

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
st.set_page_config(page_title="Screener Debug", layout="wide")

# --- ACCÈS AUX SECRETS OANDA ---
try:
    OANDA_ACCESS_TOKEN = st.secrets["OANDA_ACCESS_TOKEN"]
except KeyError:
    st.error("🔑 Secret OANDA_ACCESS_TOKEN non trouvé !"); st.stop()

# --- CONSTANTES ---
INSTRUMENTS_LIST = ['EUR_USD', 'GBP_USD', 'XAU_USD'] # Liste minimale pour un test rapide
TIMEZONE = 'Europe/Paris'

# ==============================================================================
# 1. FONCTIONS DE CALCUL ET DE LOGIQUE (AVEC DÉBOGAGE)
# ==============================================================================

# ### CORRECTION : La fonction retourne maintenant les données OU un message d'erreur
@st.cache_data(ttl=10, show_spinner=False) 
def fetch_data_debug(pair, timeframe):
    api = API(access_token=OANDA_ACCESS_TOKEN, environment="practice")
    params = {'granularity': timeframe, 'count': 2, 'price': 'M'}
    try:
        r = instruments.InstrumentsCandles(instrument=pair, params=params)
        api.request(r)
        # Si la requête réussit mais qu'il n'y a pas de bougies, c'est aussi un problème
        if 'candles' not in r.response or not r.response['candles']:
            return f"Réponse OK mais pas de bougies pour {pair} sur {timeframe}."
        # Si tout va bien, on retourne "Success"
        return "Success"
    except Exception as e:
        # Si une exception se produit, on retourne le message d'erreur exact
        return f"Échec API pour {pair} sur {timeframe}: {str(e)}"

# ==============================================================================
# 2. LOGIQUE PRINCIPALE DE DÉBOGAGE
# ==============================================================================
def run_debug_analysis(instruments_list):
    debug_logs = []
    progress_bar = st.progress(0, text="Lancement du test de connexion...")
    
    for i, instrument in enumerate(instruments_list):
        progress_text = f"Test de {instrument.replace('_', '/')}... ({i+1}/{len(instruments_list)})"
        progress_bar.progress((i + 1) / len(instruments_list), text=progress_text)
        
        # On teste une seule timeframe pour être rapide
        result = fetch_data_debug(instrument, 'H1')
        debug_logs.append(result)
        
    progress_bar.empty()
    return debug_logs

# ==============================================================================
# 4. INTERFACE UTILISATEUR DE DÉBOGAGE
# ==============================================================================
st.markdown('<h1 style="text-align: center;">🕵️‍♂️ Outil de Débogage API OANDA</h1>', unsafe_allow_html=True)
st.info("Cette page teste la connexion à l'API OANDA pour chaque instrument et affiche le résultat brut. Cela nous aidera à trouver la source du problème.")

if st.button("🚀 Lancer le test de connexion", use_container_width=True, type="primary"):
    with st.spinner("Test en cours..."):
        st.session_state.debug_logs = run_debug_analysis(INSTRUMENTS_LIST)
        st.session_state.debug_done = True

if 'debug_done' in st.session_state and st.session_state.debug_done:
    st.subheader("Résultats du test de connexion :")
    
    success_count = sum(1 for log in st.session_state.debug_logs if log == "Success")
    
    if success_count == len(INSTRUMENTS_LIST):
        st.success("✅ Connexion réussie pour tous les instruments testés ! Le problème vient de la logique de calcul des indicateurs.")
    elif success_count > 0:
        st.warning(f"⚠️ Connexion partielle ({success_count}/{len(INSTRUMENTS_LIST)} réussites). Certains instruments échouent.")
    else:
        st.error("❌ Échec total de la connexion. Aucune donnée n'a pu être récupérée. Le problème vient probablement de la clé API ou d'une restriction du compte.")

    with st.expander("Voir les logs détaillés pour chaque instrument"):
        for log in st.session_state.debug_logs:
            if log == "Success":
                st.markdown(f"<p style='color:lightgreen;'>- {log}</p>", unsafe_allow_html=True)
            else:
                st.markdown(f"<p style='color:lightcoral;'>- {log}</p>", unsafe_allow_html=True)

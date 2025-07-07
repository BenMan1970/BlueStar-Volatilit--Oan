# --- START OF FILE app.py (VERSION OANDA MINIMALISTE) ---

import streamlit as st
import pandas as pd
import numpy as np
import warnings
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments

warnings.filterwarnings('ignore')

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="OANDA Test", page_icon="🌐", layout="wide")

# --- ACCÈS AUX SECRETS OANDA ---
try:
    OANDA_ACCESS_TOKEN = st.secrets["OANDA_ACCESS_TOKEN"]
except KeyError:
    st.error("🔑 Secret OANDA_ACCESS_TOKEN non trouvé !"); st.stop()

# --- FONCTION DE TEST ---
@st.cache_data(ttl=10) # Cache court pour les tests
def test_oanda_connection(instrument):
    api = API(access_token=OANDA_ACCESS_TOKEN, environment="practice")
    params = {'count': 5, 'granularity': 'H1'}
    try:
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        response = api.request(r)
        
        # On vérifie si la réponse contient des bougies
        if 'candles' in response and len(response['candles']) > 0:
            return f"✅ Succès pour {instrument}: {len(response['candles'])} bougies reçues."
        else:
            # Si la réponse est vide ou mal formée
            return f"❌ Échec pour {instrument}: Réponse reçue mais vide ou malformée. Réponse: {response}"
            
    except Exception as e:
        # Si la librairie lève une exception (erreur de token, etc.)
        return f"❌ ERREUR API pour {instrument}: {str(e)}"

# --- INTERFACE ---
st.header("Test de Connexion Final - OANDA")
st.info("Ce test tente de récupérer 5 bougies H1 pour quelques instruments. Si cela échoue, le problème est définitivement lié à l'API OANDA ou à votre compte.")

# Liste d'instruments pour le test
test_instruments = ['EUR_USD', 'XAU_USD']

if st.button("Lancer le test OANDA", type="primary"):
    with st.spinner("Test en cours..."):
        for instrument in test_instruments:
            result = test_oanda_connection(instrument)
            if "Succès" in result:
                st.success(result)
            else:
                st.error(result)

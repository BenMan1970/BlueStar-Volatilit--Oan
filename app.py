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
import pytz # <--- CORRECTION : Import manquant

warnings.filterwarnings('ignore')

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Forex Intraday Screener Pro",
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
FOREX_PAIRS = [
    'EUR_USD', 'USD_JPY', 'GBP_USD', 'USD_CHF', 'AUD_USD', 'USD_CAD', 'NZD_USD', 
    'EUR_JPY', 'GBP_JPY', 'CHF_JPY', 'AUD_JPY', 'CAD_JPY', 'NZD_JPY',
    'EUR_GBP', 'EUR_AUD', 'EUR_CAD', 'EUR_CHF', 'EUR_NZD',
    'GBP_AUD', 'GBP_CAD', 'GBP_CHF', 'GBP_NZD'
]
TIMEZONE = 'Europe/Paris'

# ==============================================================================
# 1. FONCTIONS DE RÉCUPÉRATION ET DE CALCUL
# ==============================================================================

@st.cache_data(ttl=600, show_spinner="Fetching OANDA data...")
def fetch_multi_timeframe_data(pair, timeframes=['D', 'H4', 'H1']):
    """Récupère les données pour plusieurs timeframes pour une seule paire."""
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
            # Les données OANDA sont en UTC, on les localise
            df['Time'] = pd.to_datetime(df['Time']).dt.tz_localize('UTC').dt.tz_convert(TIMEZONE)
            all_data[tf] = df
        except Exception:
            continue
    return all_data

def calculate_all_indicators(df):
    """Calcule tous les indicateurs nécessaires sur un DataFrame."""
    if df is None or len(df) < 50: return None
    
    # Tendance via les EMAs
    df['ema_fast'] = ta.trend.ema_indicator(df['Close'], window=21)
    df['ema_slow'] = ta.trend.ema_indicator(df['Close'], window=50)
    
    # Indicateurs de volatilité et de force
    df['atr'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
    adx_indicator = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'], window=14)
    df['adx'] = adx_indicator.adx()
    df['dmi_plus'] = adx_indicator.adx_pos()
    df['dmi_minus'] = adx_indicator.adx_neg()
    
    # Momentum
    df['rsi'] = ta.momentum.rsi(df['Close'], window=14)
    
    return df.dropna()

def determine_trend(df_row):
    """Détermine la tendance ('Bullish', 'Bearish', 'Neutral') à partir d'une ligne de données."""
    if df_row['ema_fast'] > df_row['ema_slow']:
        return 'Bullish'
    elif df_row['ema_fast'] < df_row['ema_slow']:
        return 'Bearish'
    return 'Neutral'

def find_sr_levels(df, lookback=50):
    """Trouve les niveaux de support et résistance les plus proches."""
    recent_df = df.tail(lookback)
    price = recent_df['Close'].iloc[-1]
    
    # find_peaks retourne les index des pics
    res_idx, _ = find_peaks(recent_df['High'], distance=5, prominence=0.001)
    sup_idx, _ = find_peaks(-recent_df['Low'], distance=5, prominence=0.001)
    
    resistances = recent_df['High'].iloc[res_idx]
    supports = recent_df['Low'].iloc[sup_idx]
    
    # Filtrer les niveaux pertinents (au-dessus/en dessous du prix actuel)
    next_res = resistances[resistances > price].min() if not resistances[resistances > price].empty else np.nan
    next_sup = supports[supports < price].max() if not supports[supports < price].empty else np.nan
    
    dist_to_res = ((next_res - price) / price) * 100 if pd.notna(next_res) else np.nan
    dist_to_sup = ((price - next_sup) / price) * 100 if pd.notna(next_sup) else np.nan
    
    return next_sup, next_res, dist_to_sup, dist_to_res


# ==============================================================================
# 2. LOGIQUE PRINCIPALE D'ANALYSE ET DE FILTRAGE
# ==============================================================================

def run_full_analysis(pairs_list, params):
    """Exécute l'analyse complète sur toutes les paires et retourne les paires filtrées."""
    filtered_pairs = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, pair in enumerate(pairs_list):
        status_text.text(f"Analyse de {pair.replace('_', '/')}... ({i+1}/{len(pairs_list)})")
        
        # 1. Récupération des données
        multi_tf_data = fetch_multi_timeframe_data(pair, timeframes=['D', 'H4', 'H1'])
        if not all(tf in multi_tf_data for tf in ['D', 'H4', 'H1']):
            continue

        # 2. Calcul des indicateurs pour chaque timeframe
        data_D = calculate_all_indicators(multi_tf_data['D'])
        data_H4 = calculate_all_indicators(multi_tf_data['H4'])
        data_H1 = calculate_all_indicators(multi_tf_data['H1'])

        if data_D is None or data_H4 is None or data_H1 is None:
            continue
            
        # 3. Extraction des dernières valeurs
        last_D, last_H4, last_H1 = data_D.iloc[-1], data_H4.iloc[-1], data_H1.iloc[-1]
        price = last_H1['Close']
        score = 0
        
        # --- APPLICATION DES FILTRES ---
        
        # Condition A: Volatilité suffisante (sur le Daily)
        atr_percent = (last_D['atr'] / price) * 100
        if atr_percent < params['min_atr_percent']: continue
        score += 25

        # Condition B: Tendance forte et unidirectionnelle (H4 & H1)
        trend_H4 = determine_trend(last_H4)
        trend_H1 = determine_trend(last_H1)
        
        adx_strong_H4 = last_H4['adx'] > params['min_adx']
        adx_strong_H1 = last_H1['adx'] > params['min_adx']
        
        if not (adx_strong_H4 and adx_strong_H1): continue
        score += 25

        # Condition C: Alignement des tendances
        if trend_H1 != trend_H4 or trend_H1 == 'Neutral': continue
        score += 25
        
        # Vérification de la directionnalité du DMI
        direction = ""
        if trend_H1 == 'Bullish' and last_H1['dmi_plus'] > last_H1['dmi_minus'] and last_H4['dmi_plus'] > last_H4['dmi_minus']:
            direction = 'Achat'
        elif trend_H1 == 'Bearish' and last_H1['dmi_minus'] > last_H1['dmi_plus'] and last_H4['dmi_minus'] > last_H4['dmi_plus']:
            direction = 'Vente'
        else:
            continue # Le DMI ne confirme pas la tendance des EMAs

        # Condition D: RSI dans une zone favorable
        if not (params['rsi_min'] < last_H1['rsi'] < params['rsi_max']): continue
        score += 25
        
        # 4. Informations supplémentaires
        sup, res, dist_sup, dist_res = find_sr_levels(multi_tf_data['H1'])

        # Si on arrive ici, la paire a passé tous les filtres
        filtered_pairs.append({
            'Paire': pair.replace('_', '/'),
            'Direction': direction,
            'Prix': price,
            'ATR (D) %': atr_percent,
            'ADX H1': last_H1['adx'],
            'ADX H4': last_H4['adx'],
            'RSI H1': last_H1['rsi'],
            'Prochain Supp': sup,
            'Prochaine Rés': res,
            'Score': score
        })
        progress_bar.progress((i + 1) / len(pairs_list))

    status_text.empty()
    progress_bar.empty()
    return pd.DataFrame(filtered_pairs)


# ==============================================================================
# 3. INTERFACE UTILISATEUR (STREAMLIT)
# ==============================================================================

st.markdown('<h1 class="screener-header">🎯 Forex Intraday Screener Pro</h1>', unsafe_allow_html=True)

# --- BARRE LATÉRALE DE CONTRÔLES ---
with st.sidebar:
    st.header("🛠️ Paramètres du Filtre")
    params = {
        'min_atr_percent': st.slider("ATR (Daily) Minimum %", 0.1, 2.0, 0.5, 0.1, help="Volatilité minimale requise."),
        'min_adx': st.slider("ADX Minimum (H1 & H4)", 15, 30, 20, 1, help="Force de tendance minimale."),
        'rsi_min': st.slider("RSI H1 Minimum", 10, 40, 30, 1),
        'rsi_max': st.slider("RSI H1 Maximum", 60, 90, 70, 1),
    }

# --- LOGIQUE DE SCAN ---
if 'scan_done' not in st.session_state:
    st.session_state.scan_done = False

col1, col2, _ = st.columns([1.5, 1.5, 5])
with col1:
    if st.button("🔎 Lancer / Rescan", use_container_width=True, type="primary"):
        st.session_state.scan_done = False
        st.cache_data.clear()
        st.rerun() # Rerun pour relancer la logique de scan

# La logique de scan doit être en dehors du bouton pour s'exécuter après le rerun
if not st.session_state.scan_done:
    with st.spinner("Analyse en cours..."):
        st.session_state.results_df = run_full_analysis(FOREX_PAIRS, params)
        st.session_state.scan_time = datetime.now()
        st.session_state.scan_done = True
        st.rerun()

# --- AFFICHAGE DES RÉSULTATS ---
if st.session_state.scan_done and 'results_df' in st.session_state:
    df = st.session_state.results_df
    # CORRECTION : Utiliser pytz pour la conversion de fuseau horaire
    scan_time_str = st.session_state.scan_time.astimezone(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")

    st.markdown(f'<div class="update-info">🔄 Scan terminé à {scan_time_str} ({TIMEZONE})</div>', unsafe_allow_html=True)
    
    if df.empty:
        st.info("Aucune paire ne correspond à tous les critères de filtrage. Essayez d'assouplir les paramètres.")
    else:
        st.subheader(f"🏆 {len(df)} Opportunités trouvées")

        # Formatage pour l'affichage
        display_df = df.copy()
        for col in ['Prix', 'ATR (D) %', 'ADX H1', 'ADX H4', 'RSI H1', 'Prochain Supp', 'Prochaine Rés']:
            display_df[col] = display_df[col].map('{:.2f}'.format)
        
        # Coloration du DataFrame
        def style_dataframe(df_to_style):
            def style_direction(direction):
                color = 'lightgreen' if direction == 'Achat' else 'lightcoral'
                return f'color: {color}; font-weight: bold;'
            
            return df_to_style.style.applymap(style_direction, subset=['Direction'])
        
        st.dataframe(style_dataframe(display_df.set_index('Paire')), use_container_width=True)
        
        # Bouton d'export PDF (à implémenter)
        with col2:
            st.download_button(
                label="📄 Exporter en PDF",
                data=b"", # Remplacer par la fonction de génération PDF
                file_name=f"Screener_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

# --- GUIDE UTILISATEUR ---
with st.expander("ℹ️ Comprendre la Stratégie et les Colonnes"):
    st.markdown("""
    Cette application filtre les paires de devises en se basant sur une confluence de conditions pour le trading intraday :
    - **Condition A (Volatilité)**: L'ATR sur le graphique journalier doit être supérieur au seuil défini (ex: > 0.5% du prix).
    - **Condition B (Force de Tendance)**: L'ADX sur H1 et H4 doit être supérieur au seuil (ex: > 20) pour confirmer une tendance forte.
    - **Condition C (Alignement)**: La tendance (définie par les EMA 21/50) doit être la même sur H1 et H4. Le DMI doit aussi confirmer la direction.
    - **Condition D (Momentum)**: Le RSI sur H1 doit être dans une zone "saine" (ex: entre 30 et 70) pour éviter les entrées sur des marchés déjà sur-étendus.
    - **Score**: Une note sur 100 indiquant la robustesse du signal (25 points par condition majeure remplie).
    - **Support/Résistance**: Les niveaux de prix clés les plus proches, identifiés sur le graphique H1.
    """)

# --- END OF FILE app.py ---

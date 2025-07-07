# app.py
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import ta

# Configuration
st.set_page_config(page_title="Forex Volatility Scanner", layout="wide")

# Liste des paires Forex majeures
FOREX_PAIRS = [
    'EURUSD=X', 'USDJPY=X', 'GBPUSD=X', 'USDCHF=X', 'AUDUSD=X',
    'USDCAD=X', 'NZDUSD=X', 'EURJPY=X', 'EURGBP=X', 'EURCHF=X',
    'EURCAD=X', 'EURAUD=X', 'GBPJPY=X', 'GBPCHF=X', 'GBPCAD=X',
    'GBPAUD=X', 'AUDJPY=X', 'AUDCAD=X', 'CADJPY=X', 'CHFJPY=X'
]

# Fonction pour récupérer les données
@st.cache_data(ttl=300)
def get_fx_data(pair, period='1d', interval='15m'):
    try:
        df = yf.download(pair, period=period, interval=interval, progress=False)
        if df.empty:
            return pd.DataFrame()
        return df
    except:
        return pd.DataFrame()

# Calcul des indicateurs techniques
def calculate_indicators(df):
    if df.empty:
        return df
    
    # Calcul ATR
    df['atr'] = ta.volatility.AverageTrueRange(
        high=df['High'], low=df['Low'], close=df['Close'], window=14
    ).average_true_range()
    
    # Calcul ADX et DMI
    adx_indicator = ta.trend.ADXIndicator(
        high=df['High'], low=df['Low'], close=df['Close'], window=14
    )
    df['adx'] = adx_indicator.adx()
    df['dmi_plus'] = adx_indicator.adx_pos()
    df['dmi_minus'] = adx_indicator.adx_neg()
    
    # Dérnière valeur seulement
    last_close = df['Close'].iloc[-1]
    return pd.Series({
        'Price': last_close,
        'ATR': df['atr'].iloc[-1],
        'ATR %': (df['atr'].iloc[-1] / last_close) * 100,
        'ADX': df['adx'].iloc[-1],
        'DMI+': df['dmi_plus'].iloc[-1],
        'DMI-': df['dmi_minus'].iloc[-1],
        'Trend': 'Bullish' if df['dmi_plus'].iloc[-1] > df['dmi_minus'].iloc[-1] else 'Bearish'
    })

# Génération des signaux
def generate_signals(row):
    if row['ADX'] < 20:
        return 'No Trend'
    
    if row['ATR %'] < 0.5:
        return 'Low Volatility'
    
    if row['Trend'] == 'Bullish' and row['DMI+'] > 25:
        sl = row['Price'] - (1.5 * row['ATR'])
        tp = row['Price'] + (3 * row['ATR'])
        return f'BUY | SL: {sl:.5f} | TP: {tp:.5f}'
    
    if row['Trend'] == 'Bearish' and row['DMI-'] > 25:
        sl = row['Price'] + (1.5 * row['ATR'])
        tp = row['Price'] - (3 * row['ATR'])
        return f'SELL | SL: {sl:.5f} | TP: {tp:.5f}'
    
    return 'Wait'

# Interface Streamlit
st.title('📈 Forex Volatility Scanner')
st.markdown("""
**Scan des paires forex avec filtres ATR (volatilité) et ADX (force de tendance)**
""")

# Paramètres
col1, col2, col3 = st.columns(3)
with col1:
    timeframe = st.selectbox('Timeframe', ['15m', '30m', '1h', '4h'], index=2)
with col2:
    period_map = {'15m': '3d', '30m': '5d', '1h': '7d', '4h': '15d'}
    period = period_map[timeframe]
with col3:
    min_adx = st.slider('ADX Minimum', 15, 30, 20)

# Téléchargement des données
progress_bar = st.progress(0)
data = []

for i, pair in enumerate(FOREX_PAIRS):
    df = get_fx_data(pair, period=period, interval=timeframe)
    if not df.empty:
        pair_data = calculate_indicators(df)
        pair_data['Pair'] = pair.replace('=X', '')
        data.append(pair_data)
    progress_bar.progress((i + 1) / len(FOREX_PAIRS))

# Création du DataFrame
if data:
    results_df = pd.DataFrame(data).set_index('Pair')
    
    # Application des filtres
    results_df['Signal'] = results_df.apply(generate_signals, axis=1)
    filtered_df = results_df[results_df['Signal'].str.contains('BUY|SELL')]
    
    # Formatage
    filtered_df['ATR %'] = filtered_df['ATR %'].map('{:.2f}%'.format)
    filtered_df['ADX'] = filtered_df['ADX'].map('{:.1f}'.format)
    filtered_df['DMI+'] = filtered_df['DMI+'].map('{:.1f}'.format)
    filtered_df['DMI-'] = filtered_df['DMI-'].map('{:.1f}'.format)
    
    # Affichage des résultats
    st.subheader(f'Signaux de Trading ({timeframe} timeframe)')
    st.dataframe(filtered_df[['Price', 'ATR %', 'ADX', 'DMI+', 'DMI-', 'Trend', 'Signal']], 
                 height=600)
    
    # Téléchargement CSV
    csv = filtered_df.to_csv().encode('utf-8')
    st.download_button(
        label="Exporter les signaux CSV",
        data=csv,
        file_name=f'forex_signals_{timeframe}.csv',
        mime='text/csv'
    )
else:
    st.warning("Aucune donnée disponible. Veuillez réessayer plus tard.")

# Documentation
st.subheader('📚 Paramètres du Scanner')
st.markdown("""
- **ATR %**: Volatilité (Minimum 0.5% requis)
- **ADX**: Force de la tendance (Minimum 20 requis)
- **DMI+/-**: Directional Movement Indicators
- **Trend**: Direction de la tendance basée sur DMI
- **Signal**: Signal de trading avec Stop Loss (SL) et Take Profit (TP)
""")

# Footer
st.markdown("---")
st.caption("Application développée avec Streamlit | Données: Yahoo Finance | Mise à jour toutes les 5 minutes")

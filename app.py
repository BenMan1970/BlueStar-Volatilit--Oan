# --- START OF FILE app.py ---

import streamlit as st
import pandas as pd
import numpy as np
import warnings
from datetime import datetime
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
from fpdf import FPDF
import ta  # Bibliothèque pour les indicateurs techniques

warnings.filterwarnings('ignore')

# --- Configuration de la page Streamlit ---
st.set_page_config(
    page_title="Volatility & Trend Screener (OANDA)",
    page_icon="⚡",
    layout="wide"
)

# --- CSS personnalisé (similaire à l'autre app) ---
st.markdown("""
<style>
    .main > div { padding-top: 2rem; }
    .screener-header { font-size: 28px; font-weight: bold; color: #FAFAFA; margin-bottom: 15px; text-align: center; }
    .update-info { background-color: #262730; padding: 8px 15px; border-radius: 5px; margin-bottom: 20px; font-size: 14px; color: #A9A9A9; border: 1px solid #333A49; text-align: center; }
    /* Style pour le DataFrame */
    .stDataFrame { font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# --- Accès aux secrets OANDA ---
try:
    OANDA_ACCOUNT_ID = st.secrets["OANDA_ACCOUNT_ID"]
    OANDA_ACCESS_TOKEN = st.secrets["OANDA_ACCESS_TOKEN"]
except KeyError:
    st.error("🔑 Secrets OANDA non trouvés ! Veuillez les configurer dans les paramètres de l'application.")
    st.code('OANDA_ACCOUNT_ID = "..."\nOANDA_ACCESS_TOKEN = "..."')
    st.stop()

# --- Constantes et Mappages ---
FOREX_PAIRS = [
    'EUR/USD', 'USD/JPY', 'GBP/USD', 'USD/CHF', 'AUD/USD', 'USD/CAD', 'NZD/USD', 
    'EUR/JPY', 'GBP/JPY', 'CHF/JPY', 'AUD/JPY', 'CAD/JPY', 'NZD/JPY',
    'EUR/GBP', 'EUR/AUD', 'EUR/CAD', 'EUR/CHF', 'EUR/NZD',
    'GBP/AUD', 'GBP/CAD', 'GBP/CHF', 'GBP/NZD'
]

TIMEFRAME_MAP = {
    '15 minutes': 'M15',
    '30 minutes': 'M30',
    '1 heure': 'H1',
    '4 heures': 'H4',
    'Journalier': 'D'
}

# --- Fonctions de l'application ---

@st.cache_data(ttl=300, show_spinner="Fetching OANDA data...")
def get_oanda_data(pair, granularity):
    api = API(access_token=OANDA_ACCESS_TOKEN, environment="practice")
    instrument = pair.replace('/', '_')
    params = {'granularity': granularity, 'count': 250} # Assez de données pour les calculs
    try:
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        api.request(r)
        data = [{'Time': c['time'], 'Open': float(c['mid']['o']), 'High': float(c['mid']['h']), 
                 'Low': float(c['mid']['l']), 'Close': float(c['mid']['c'])} 
                for c in r.response['candles']]
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df['Time'] = pd.to_datetime(df['Time'])
        return df
    except Exception as e:
        # st.warning(f"Could not fetch data for {pair}: {e}")
        return pd.DataFrame()

def calculate_indicators(df):
    if df.empty or len(df) < 20: # Besoin d'assez de données pour ADX/ATR 14
        return None
    
    # Calcul ATR (Average True Range)
    df['atr'] = ta.volatility.AverageTrueRange(
        high=df['High'], low=df['Low'], close=df['Close'], window=14
    ).average_true_range()
    
    # Calcul ADX (Average Directional Movement Index) et DMI
    adx_indicator = ta.trend.ADXIndicator(
        high=df['High'], low=df['Low'], close=df['Close'], window=14
    )
    df['adx'] = adx_indicator.adx()
    df['dmi_plus'] = adx_indicator.adx_pos()
    df['dmi_minus'] = adx_indicator.adx_neg()

    df.dropna(inplace=True)
    if df.empty:
        return None

    last_row = df.iloc[-1]
    return pd.Series({
        'Price': last_row['Close'],
        'ATR': last_row['atr'],
        'ATR %': (last_row['atr'] / last_row['Close']) * 100,
        'ADX': last_row['adx'],
        'DMI+': last_row['dmi_plus'],
        'DMI-': last_row['dmi_minus'],
        'Trend': 'Bullish' if last_row['dmi_plus'] > last_row['dmi_minus'] else 'Bearish'
    })

def generate_signals(row, min_adx_value):
    if row['ADX'] < min_adx_value:
        return 'Range (ADX faible)'
    
    if row['ATR %'] < 0.2: # Seuil de volatilité minimum
        return 'Faible Volatilité'
    
    # Condition d'achat
    if row['Trend'] == 'Bullish' and row['DMI+'] > row['DMI-']:
        sl = row['Price'] - (1.5 * row['ATR'])
        tp = row['Price'] + (3 * row['ATR'])
        return f'ACHAT | SL: {sl:.5f} | TP: {tp:.5f}'
    
    # Condition de vente
    if row['Trend'] == 'Bearish' and row['DMI-'] > row['DMI+']:
        sl = row['Price'] + (1.5 * row['ATR'])
        tp = row['Price'] - (3 * row['ATR'])
        return f'VENTE | SL: {sl:.5f} | TP: {tp:.5f}'
    
    return 'Attendre'

def create_pdf_report(df, timeframe, scan_time):
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 15)
            self.cell(0, 10, 'Rapport Volatility & Trend Screener', 0, 1, 'C')
            self.set_font('Arial', '', 9)
            self.cell(0, 8, f'Timeframe: {timeframe} | Généré le: {scan_time}', 0, 1, 'C')
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, 'Page ' + str(self.page_no()), 0, 0, 'C')

    pdf = PDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    # Couleurs
    header_color = (23, 34, 56)
    buy_color = (46, 139, 87)
    sell_color = (178, 34, 34)

    # Entête du tableau
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(*header_color)
    pdf.set_text_color(255, 255, 255)
    
    col_widths = {'Pair': 25, 'Price': 25, 'ATR %': 20, 'ADX': 15, 'Signal': 185}
    for col_name, width in col_widths.items():
        pdf.cell(width, 10, col_name, 1, 0, 'C', True)
    pdf.ln()

    # Corps du tableau
    pdf.set_font('Arial', '', 9)
    pdf.set_text_color(0, 0, 0)
    
    for _, row in df.iterrows():
        # Définir la couleur du texte pour le signal
        if 'ACHAT' in row['Signal']:
            pdf.set_text_color(*buy_color)
        elif 'VENTE' in row['Signal']:
            pdf.set_text_color(*sell_color)
        else:
            pdf.set_text_color(128, 128, 128)

        pdf.cell(col_widths['Pair'], 10, row.name, 1, 0, 'L')
        pdf.set_text_color(0, 0, 0) # Revenir au noir pour les autres colonnes
        pdf.cell(col_widths['Price'], 10, f"{row['Price']:.5f}", 1, 0, 'C')
        pdf.cell(col_widths['ATR %'], 10, f"{row['ATR %']:.2f}%", 1, 0, 'C')
        pdf.cell(col_widths['ADX'], 10, f"{row['ADX']:.1f}", 1, 0, 'C')
        
        # Remettre la couleur pour la colonne Signal
        if 'ACHAT' in row['Signal']: pdf.set_text_color(*buy_color)
        elif 'VENTE' in row['Signal']: pdf.set_text_color(*sell_color)
        else: pdf.set_text_color(128, 128, 128)
        
        pdf.cell(col_widths['Signal'], 10, row['Signal'], 1, 0, 'L')
        pdf.ln()
        pdf.set_text_color(0, 0, 0) # Réinitialiser la couleur pour la prochaine ligne

    return bytes(pdf.output())

# --- Interface Utilisateur ---
st.markdown('<h1 class="screener-header">📈 Volatility & Trend Screener (OANDA)</h1>', unsafe_allow_html=True)

# Barre latérale pour les contrôles
with st.sidebar:
    st.header("⚙️ Paramètres du Scan")
    selected_timeframe_key = st.selectbox('Timeframe', list(TIMEFRAME_MAP.keys()), index=2)
    min_adx_value = st.slider('ADX Minimum', 15, 30, 20, help="Filtre pour la force de la tendance. Une valeur plus élevée signifie une tendance plus forte.")

# Logique de scan
if 'scan_done' not in st.session_state:
    st.session_state.scan_done = False

col1, col2, _ = st.columns([1.5, 1.5, 5])
with col1:
    if st.button("⚡ Lancer / Rescan", use_container_width=True):
        st.session_state.scan_done = False # Forcer un rescan
        st.cache_data.clear()

if not st.session_state.scan_done:
    with st.spinner(f"Analyse en cours sur {len(FOREX_PAIRS)} paires ({selected_timeframe_key})..."):
        all_data = []
        progress_bar = st.progress(0)
        for i, pair in enumerate(FOREX_PAIRS):
            df = get_oanda_data(pair, TIMEFRAME_MAP[selected_timeframe_key])
            if not df.empty:
                indicators = calculate_indicators(df)
                if indicators is not None:
                    indicators['Pair'] = pair
                    all_data.append(indicators)
            progress_bar.progress((i + 1) / len(FOREX_PAIRS))
        
        if all_data:
            results_df = pd.DataFrame(all_data).set_index('Pair')
            results_df['Signal'] = results_df.apply(lambda row: generate_signals(row, min_adx_value), axis=1)
            st.session_state.results = results_df
            st.session_state.scan_time = datetime.now()
        
        st.session_state.scan_done = True
        st.rerun()

# Affichage des résultats
if st.session_state.scan_done and 'results' in st.session_state:
    results_df = st.session_state.results
    scan_time_str = st.session_state.scan_time.strftime("%Y-%m-%d %H:%M:%S")

    st.markdown(f'<div class="update-info">🔄 Dernière mise à jour : {scan_time_str} (Données OANDA)</div>', unsafe_allow_html=True)
    
    with col2:
        pdf_data = create_pdf_report(results_df, selected_timeframe_key, scan_time_str)
        st.download_button(
            label="📄 Exporter en PDF",
            data=pdf_data,
            file_name=f"Volatility_Report_{selected_timeframe_key.replace(' ', '')}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    st.subheader(f"Signaux de Trading sur {selected_timeframe_key} (ADX > {min_adx_value})")
    
    # Filtrer pour l'affichage (ne montrer que les signaux clairs)
    display_df = results_df[results_df['Signal'].str.contains('ACHAT|VENTE')]

    if display_df.empty:
        st.info("Aucun signal d'achat ou de vente correspondant aux critères actuels n'a été trouvé.")
    else:
        # Formatage pour un affichage propre
        formatted_df = display_df.copy()
        formatted_df['Price'] = formatted_df['Price'].map('{:.5f}'.format)
        formatted_df['ATR %'] = formatted_df['ATR %'].map('{:.2f}%'.format)
        formatted_df['ADX'] = formatted_df['ADX'].map('{:.1f}'.format)
        
        st.dataframe(formatted_df[['Price', 'ATR %', 'ADX', 'Trend', 'Signal']], use_container_width=True)

    with st.expander("Voir tous les résultats (y compris 'Attendre' et 'Range')"):
        st.dataframe(results_df, use_container_width=True)

else:
    st.info("Cliquez sur 'Lancer / Rescan' pour commencer l'analyse.")

# Guide et Footer
with st.expander("ℹ️ Guide des Indicateurs"):
    st.markdown("""
    - **ATR % (Average True Range Percentage)**: Mesure la volatilité en pourcentage du prix. Une valeur élevée indique une forte volatilité.
    - **ADX (Average Directional Movement Index)**: Mesure la force de la tendance, quelle que soit sa direction. Un ADX > 20-25 indique une tendance établie.
    - **DMI+ / DMI- (Directional Movement Indicators)**: Indiquent la direction de la tendance. Si DMI+ est au-dessus de DMI-, la tendance est haussière, et inversement.
    - **Signal**: Le signal de trading généré. Le Stop Loss (SL) est calculé à 1.5x l'ATR et le Take Profit (TP) à 3x l'ATR.
    """)

# --- END OF FILE app.py ---

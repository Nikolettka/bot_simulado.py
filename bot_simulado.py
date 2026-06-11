import time
import threading
import logging
import ccxt
import pandas as pd
from dash import Dash, html, dcc
from dash.dependencies import Input, Output

# Configuración de logs limpia
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger()

# Parámetros del simulador (Máximo rendimiento posible)
MIN_PROFIT = 0.3      
MAX_PROFIT = 5.0      # Subimos el máximo por si hay alta volatilidad
TAKER_FEE = 0.0010     
CAPITAL_SIMULADO = 50.0  

# Almacenamiento global para comunicar el bot con el Dashboard
data_compartida = {
    "capital_actual": CAPITAL_SIMULADO,
    "mejor_ruta": "Buscando...",
    "mejor_profit": 0.0,
    "historial_profits": []
}

def inicializar_okx_publico():
    return ccxt.okx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})

def buscar_todos_los_triangulos(markets):
    """Analiza TODO el mercado sin límites para encontrar cadenas de 3 monedas."""
    pares_spot = [symbol for symbol, market in markets.items() if market['spot'] and market['active']]
    simbolos_por_moneda = {}
    for par in pares_spot:
        base, quote = par.split('/')
        simbolos_por_moneda.setdefault(base, []).append(par)
        simbolos_por_moneda.setdefault(quote, []).append(par)

    triangulos = []
    inicio = 'USDT'
    if inicio not in simbolos_por_moneda: return []

    for par1 in simbolos_por_moneda[inicio]:
        base1, quote1 = par1.split('/')
        m1 = base1 if quote1 == inicio else quote1
        if m1 not in simbolos_por_moneda: continue
        
        for par2 in simbolos_por_moneda[m1]:
            if par2 == par1: continue
            base2, quote2 = par2.split('/')
            m2 = base2 if quote2 == m1 else quote2
            
            for par3 in simbolos_por_moneda[m2]:
                if par3 == par2 or par3 == par1: continue
                base3, quote3 = par3.split('/')
                if base3 == inicio or quote3 == inicio:
                    ruta = (par1, par2, par3)
                    if ruta not in triangulos:
                        triangulos.append(ruta)
    return triangulos

def calcular_arbitraje(exchange, triangulo, tickers):
    monto = 1.0  
    secuencia_texto = ""
    moneda_actual = "USDT"

    for i, par in enumerate(triangulo):
        ticker = tickers.get(par)
        if not ticker or not ticker['ask'] or not ticker['bid']: return -999.0, ""
        base, quote = par.split('/')

        if moneda_actual == quote:
            monto = (monto / ticker['ask']) * (1 - TAKER_FEE)
            secuencia_texto += f"{base}"
            moneda_actual = base
        else:
            monto = (monto * ticker['bid']) * (1 - TAKER_FEE)
            secuencia_texto += f"{quote}"
            moneda_actual = quote
        if i < 2: secuencia_texto += ">"

    return (monto - 1.0) * 100, secuencia_texto

def bucle_bot_segundo():
    """Hebra secundaria: Ejecuta el análisis ilimitado cada 1 segundo."""
    global CAPITAL_SIMULADO
    exchange = inicializar_okx_publico()
    logger.info("Bot ilimitado iniciado...")
    
    try:
        markets = exchange.load_markets()
        triangulos = buscar_todos_los_triangulos(markets)
        logger.info(f"Escaneando un total de {len(triangulos)} combinaciones de mercado.")
        
        while True:
            try:
                # Descargamos los tickers globales de una sola vez para ir rápido
                tickers = exchange.fetch_tickers()
                mejor_profit = -999.0
                mejor_ruta_texto = ""

                for tri in triangulos:
                    profit, texto = calcular_arbitraje(exchange, tri, tickers)
                    if profit > mejor_profit:
                        mejor_profit = profit
                        mejor_ruta_texto = texto

                # Simulación de ganancias
                if mejor_profit >= MIN_PROFIT:
                    ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                    CAPITAL_SIMULADO += ganancia
                
                # Actualizamos los datos para el Dashboard web
                data_compartida["capital_actual"] = CAPITAL_SIMULADO
                data_compartida["mejor_ruta"] = mejor_ruta_texto
                data_compartida["mejor_profit"] = mejor_profit
                data_compartida["historial_profits"].append(mejor_profit)
                if len(data_compartida["historial_profits"]) > 30:
                    data_compartida["historial_profits"].pop(0)

            except Exception as e:
                logger.error(f"Error en escaneo de precios: {e}")
            
            time.sleep(1) # Intervalo agresivo de 1 segundo

    except Exception as e:
        logger.error(f"Fallo crítico en el motor del bot: {e}")

# --- CONFIGURACIÓN DEL DASHBOARD WEB ---
app = Dash(__name__)

app.layout = html.Div(style={'backgroundColor': '#111111', 'color': '#ffffff', 'fontFamily': 'sans-serif', 'padding': '20px'}, children=[
    html.H1("🤖 OKX Arbitrage Dashboard", style={'textAlign': 'center', 'color': '#00ffcc'}),
    
    html.Div(style={'display': 'flex', 'justifyContent': 'space-around', 'flexWrap': 'wrap', 'marginTop': '20px'}, children=[
        html.Div(style={'backgroundColor': '#222222', 'padding': '20px', 'borderRadius': '10px', 'width': '250px', 'textAlign': 'center'}, children=[
            html.H3("Capital Simulado"),
            html.H2(id="live-capital", style={'color': '#00ff88'})
        ]),
        html.Div(style={'backgroundColor': '#222222', 'padding': '20px', 'borderRadius': '10px', 'width': '250px', 'textAlign': 'center'}, children=[
            html.H3("Mejor Retorno Actual"),
            html.H2(id="live-profit", style={'color': '#ff3366'})
        ])
    ]),
    
    html.Div(style={'marginTop': '30px', 'backgroundColor': '#222222', 'padding': '15px', 'borderRadius': '10px', 'textAlign': 'center'}, children=[
        html.H3("Ruta más eficiente en tiempo real:"),
        html.H4(id="live-route", style={'color': '#00ffcc', 'fontSize': '22px'})
    ]),
    
    dcc.Interval(id='interval-component', interval=2000, n_intervals=0) # Refresca la web cada 2 segundos
])

@app.callback(
    [Output('live-capital', 'children'),
     Output('live-profit', 'children'),
     Output('live-route', 'children')],
    [Input('interval-component', 'n_intervals')]
)
def update_dashboard(n):
    cap = f"${data_compartida['capital_actual']:.4f} USDT"
    prof = f"{data_compartida['mejor_profit']:.4f}%"
    ruta = data_compartida['mejor_ruta']
    return cap, prof, ruta

if __name__ == "__main__":
    # Arrancamos el bot en segundo plano para que no bloquee la interfaz web
    hilo_bot = threading.Thread(target=bucle_bot_segundo)
    hilo_bot.daemon = True
    hilo_bot.start()
    
    # Arrancamos el servidor web en el puerto asignado por Railway
    app.run(host='0.0.0.0', port=8080, debug=False)

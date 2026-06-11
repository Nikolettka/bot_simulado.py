import time
import threading
import logging
import ccxt
from dash import Dash, html, dcc
from dash.dependencies import Input, Output

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger()

# Parámetros del motor del bot
MIN_PROFIT = 0.3      
MAX_PROFIT = 5.0      
TAKER_FEE = 0.0010     
CAPITAL_SIMULADO = 50.0  

data_compartida = {
    "capital_actual": CAPITAL_SIMULADO,
    "mejor_ruta": "Escaneando OKX...",
    "mejor_profit": 0.0,
    "total_triangulos": 0,
    "tiempo_escaneo": 0.0,
    "ultimos_spreads": [0.0] * 10, # Para la gráfica de barras CSS
    "transacciones": []  
}

def inicializar_okx_publico():
    return ccxt.okx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})

def buscar_todos_los_triangulos(markets):
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
                    if ruta not in triangulos: triangulos.append(ruta)
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
    global CAPITAL_SIMULADO
    exchange = inicializar_okx_publico()
    
    try:
        markets = exchange.load_markets()
        triangulos = buscar_todos_los_triangulos(markets)
        data_compartida["total_triangulos"] = len(triangulos)
        
        while True:
            try:
                t_inicio = time.time()
                tickers = exchange.fetch_tickers()
                mejor_profit = -999.0
                mejor_ruta_texto = ""

                for tri in triangulos:
                    profit, texto = calcular_arbitraje(exchange, tri, tickers)
                    if profit > mejor_profit:
                        mejor_profit = profit
                        mejor_ruta_texto = texto

                # Registrar la ganancia si se cruza el umbral
                if mejor_profit >= MIN_PROFIT:
                    ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                    CAPITAL_SIMULADO += ganancia
                    
                    nueva_tx = {
                        "Hora": time.strftime("%H:%M:%S"),
                        "Ruta": mejor_ruta_texto,
                        "Rendimiento": f"+{mejor_profit:.2f}%",
                        "Resultado": f"${CAPITAL_SIMULADO:.2f}"
                    }
                    data_compartida["transacciones"].insert(0, nueva_tx)
                    if len(data_compartida["transacciones"]) > 5:
                        data_compartida["transacciones"].pop()

                # Guardar métricas en tiempo real
                data_compartida["capital_actual"] = CAPITAL_SIMULADO
                data_compartida["mejor_ruta"] = mejor_ruta_texto
                data_compartida["mejor_profit"] = mejor_profit
                data_compartida["tiempo_escaneo"] = time.time() - t_inicio
                
                # Historial para la gráfica de barras interactiva
                data_compartida["ultimos_spreads"].append(mejor_profit)
                if len(data_compartida["ultimos_spreads"]) > 10:
                    data_compartida["ultimos_spreads"].pop(0)

            except Exception as e:
                logger.error(f"Error ciclo: {e}")
            time.sleep(1)

    except Exception as e:
        logger.error(f"Fallo crítico: {e}")

# --- ENTORNO WEB REDISEÑADO ---
app = Dash(__name__)

app.layout = html.Div(style={'backgroundColor': '#12161a', 'color': '#ffffff', 'fontFamily': 'sans-serif', 'padding': '12px', 'minHeight': '100vh'}, children=[
    html.H2("⚡ OKX ARBITRAGE PRO", style={'textAlign': 'center', 'color': '#eaecef', 'fontSize': '20px', 'letterSpacing': '1px', 'borderBottom': '1px solid #2b3139', 'paddingBottom': '10px'}),
    
    # Capital formateado a $50.00
    html.Div(style={'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '18px', 'marginTop': '12px'}, children=[
        html.Div("Capital Simulado Disponible", style={'color': '#848e9c', 'fontSize': '13px', 'textAlign': 'center'}),
        html.Div(id="live-capital", style={'color': '#02c076', 'fontSize': '34px', 'fontWeight': 'bold', 'textAlign': 'center', 'marginTop': '3px'})
    ]),
    
    # Datos de Estado
    html.Div(style={'display': 'flex', 'gap': '10px', 'marginTop': '12px'}, children=[
        html.Div(style={'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '12px', 'flex': '1', 'textAlign': 'center'}, children=[
            html.Div("Spread Máximo", style={'color': '#848e9c', 'fontSize': '12px'}),
            html.Div(id="live-profit", style={'fontSize': '18px', 'fontWeight': 'bold', 'marginTop': '3px'})
        ]),
        html.Div(style={'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '12px', 'flex': '1', 'textAlign': 'center'}, children=[
            html.Div("Filtro Mínimo", style={'color': '#848e9c', 'fontSize': '12px'}),
            html.Div(f"+{MIN_PROFIT}%", style={'color': '#f0b90b', 'fontSize': '18px', 'fontWeight': 'bold', 'marginTop': '3px'})
        ])
    ]),
    
    # Ruta en tiempo real
    html.Div(style={'marginTop': '12px', 'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '12px'}, children=[
        html.Div("Mejor Ruta Detectada:", style={'color': '#848e9c', 'fontSize': '12px', 'marginBottom': '3px'}),
        html.Div(id="live-route", style={'color': '#f0b90b', 'fontSize': '16px', 'fontWeight': 'bold', 'textAlign': 'center', 'fontFamily': 'monospace'})
    ]),
    
    # NUEVA GRÁFICA DE BARRAS EN TIEMPO REAL (CSS NATAL)
    html.Div(style={'marginTop': '15px', 'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px'}, children=[
        html.Div("📊 Monitor de Variación de Spreads (Últimos 10s)", style={'color': '#eaecef', 'fontSize': '13px', 'fontWeight': 'bold', 'marginBottom': '15px'}),
        html.Div(id="live-bar-graph", style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'flex-end', 'height': '80px', 'padding': '0 10px', 'borderBottom': '2px solid #2b3139'})
    ]),

    # PANEL DE ESTADÍSTICAS MASIVAS
    html.Div(style={'marginTop': '15px', 'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '12px', 'display': 'flex', 'justifyContent': 'space-between'}, children=[
        html.Div(children=[
            html.Div("Rutas Escaneadas", style={'color': '#848e9c', 'fontSize': '11px'}),
            html.Div(id="live-total-tri", style={'fontSize': '14px', 'fontWeight': 'bold', 'color': '#eaecef', 'marginTop': '2px'})
        ]),
        html.Div(style={'textAlign': 'right'}, children=[
            html.Div("Velocidad de API", style={'color': '#848e9c', 'fontSize': '11px'}),
            html.Div(id="live-speed", style={'fontSize': '14px', 'fontWeight': 'bold', 'color': '#eaecef', 'marginTop': '2px'})
        ])
    ]),
    
    # Historial de trades
    html.Div(style={'marginTop': '15px', 'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '12px'}, children=[
        html.Div("📋 Registro de Operaciones Exitosas", style={'color': '#eaecef', 'fontSize': '14px', 'fontWeight': 'bold', 'borderBottom': '1px solid #2b3139', 'paddingBottom': '6px', 'marginBottom': '8px'}),
        html.Div(id="live-table")
    ]),
    
    dcc.Interval(id='interval-component', interval=1000, n_intervals=0) # Frecuencia rápida al segundo
])

@app.callback(
    [Output('live-capital', 'children'),
     Output('live-profit', 'children'),
     Output('live-route', 'children'),
     Output('live-bar-graph', 'children'),
     Output('live-total-tri', 'children'),
     Output('live-speed', 'children'),
     Output('live-table', 'children')],
    [Input('interval-component', 'n_intervals')]
)
def update_dashboard(n):
    # Formato $50.00 exactos
    cap = f"${data_compartida['capital_actual']:.2f}"
    
    profit_actual = data_compartida['mejor_profit']
    color_profit = '#02c076' if profit_actual >= MIN_PROFIT else '#f84960'
    prof = html.Span(f"{profit_actual:.4f}%", style={'color': color_profit})
    
    ruta = data_compartida['mejor_ruta']
    total_tri = f"{data_compartida['total_triangulos']:,} caminos"
    velocidad = f"{data_compartida['tiempo_escaneo']:.2f}s"
    
    # Construcción de las barras de la gráfica en CSS
    barras = []
    for val in data_compartida["ultimos_spreads"]:

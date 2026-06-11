import time
import threading
import logging
import ccxt
from dash import Dash, html, dcc
from dash.dependencies import Input, Output

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger()

# Parámetros del simulador agresivo
MIN_PROFIT = 0.3      
MAX_PROFIT = 5.0      
TAKER_FEE = 0.0010     
CAPITAL_SIMULADO = 50.0  

data_compartida = {
    "capital_actual": CAPITAL_SIMULADO,
    "mejor_ruta": "Inicializando API...",
    "mejor_profit": 0.0,
    "total_triangulos": 0,
    "tiempo_escaneo": 0.0,
    "transacciones_html": [html.Div("Esperando oportunidades (>= 0.3%)...", style={'color': '#848e9c', 'textAlign': 'center', 'padding': '15px'})]
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
    registro_trades = []
    
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

                if mejor_profit >= MIN_PROFIT:
                    ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                    CAPITAL_SIMULADO += ganancia
                    
                    nueva_fila = html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'padding': '10px 5px', 'borderBottom': '1px solid #2b3139'}, children=[
                        html.Span(time.strftime("%H:%M:%S"), style={'color': '#848e9c'}),
                        html.Span(mejor_ruta_texto, style={'fontWeight': 'bold', 'color': '#eaecef'}),
                        html.Span(f"+{mejor_profit:.2f}%", style={'color': '#02c076', 'fontWeight': 'bold'}),
                        html.Span(f"${CAPITAL_SIMULADO:.2f}", style={'color': '#ffffff', 'fontWeight': 'bold'})
                    ])
                    registro_trades.insert(0, nueva_fila)
                    if len(registro_trades) > 5:
                        registro_trades.pop()
                    data_compartida["transacciones_html"] = list(registro_trades)

                data_compartida["capital_actual"] = CAPITAL_SIMULADO
                data_compartida["mejor_ruta"] = mejor_ruta_texto
                data_compartida["mejor_profit"] = mejor_profit
                data_compartida["tiempo_escaneo"] = time.time() - t_inicio

            except Exception as e:
                logger.error(f"Error ciclo: {e}")
            time.sleep(1)

    except Exception as e:
        logger.error(f"Fallo critico: {e}")

# --- ENTORNO WEB OSCURO REESTRUCTURADO ---
app = Dash(__name__)

app.layout = html.Div(style={'backgroundColor': '#12161a', 'color': '#ffffff', 'fontFamily': 'sans-serif', 'padding': '15px', 'minHeight': '100vh'}, children=[
    html.H2("⚡ OKX ARBITRAGE PRO", style={'textAlign': 'center', 'color': '#eaecef', 'borderBottom': '1px solid #2b3139', 'paddingBottom': '10px', 'margin': '0'}),
    
    # Tarjeta Principal de Balance
    html.Div(style={'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '20px', 'marginTop': '15px', 'textAlign': 'center'}, children=[
        html.Div("Capital Simulado Disponible", style={'color': '#848e9c', 'fontSize': '14px'}),
        html.Div(id="live-capital", style={'color': '#02c076', 'fontSize': '36px', 'fontWeight': 'bold', 'marginTop': '5px'})
    ]),
    
    # Grid de Detalles del Mercado
    html.Div(style={'display': 'flex', 'gap': '10px', 'marginTop': '15px'}, children=[
        html.Div(style={'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px', 'flex': '1', 'textAlign': 'center'}, children=[
            html.Div("Spread Maximo", style={'color': '#848e9c', 'fontSize': '13px'}),
            html.Div(id="live-profit", style={'fontSize': '20px', 'fontWeight': 'bold', 'marginTop': '5px'})
        ]),
        html.Div(style={'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px', 'flex': '1', 'textAlign': 'center'}, children=[
            html.Div("Filtro Minimo", style={'color': '#848e9c', 'fontSize': '13px'}),
            html.Div(f"+{MIN_PROFIT}%", style={'color': '#f0b90b', 'fontSize': '20px', 'fontWeight': 'bold', 'marginTop': '5px'})
        ])
    ]),
    
    # Caja de Ruta
    html.Div(style={'marginTop': '15px', 'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px'}, children=[
        html.Div("Mejor Ruta Detectada (1s):", style={'color': '#848e9c', 'fontSize': '13px', 'marginBottom': '5px'}),
        html.Div(id="live-route", style={'color': '#f0b90b', 'fontSize': '18px', 'fontWeight': 'bold', 'textAlign': 'center', 'fontFamily': 'monospace'})
    ]),

    # Detalles Tecnicos
    html.Div(style={'marginTop': '15px', 'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px', 'display': 'flex', 'justifyContent': 'space-between'}, children=[
        html.Div(children=[
            html.Div("Caminos Analizados", style={'color': '#848e9c', 'fontSize': '12px'}),
            html.Div(id="live-total-tri", style={'fontSize': '15px', 'fontWeight': 'bold', 'color': '#eaecef', 'marginTop': '3px'})
        ]),
        html.Div(style={'textAlign': 'right'}, children=[
            html.Div("Latencia Escaneo", style={'color': '#848e9c', 'fontSize': '12px'}),
            html.Div(id="live-speed", style={'fontSize': '15px', 'fontWeight': 'bold', 'color': '#eaecef', 'marginTop': '3px'})
        ])
    ]),
    
    # Historial de Operaciones
    html.Div(style={'marginTop': '20px', 'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px'}, children=[
        html.Div("📜 Registro de Operaciones Exitosas", style={'color': '#eaecef', 'fontSize': '15px', 'fontWeight': 'bold', 'borderBottom': '1px solid #2b3139', 'paddingBottom': '8px', 'marginBottom': '10px'}),
        html.Div(id="live-table")
    ]),
    
    dcc.Interval(id='interval-component', interval=1000, n_intervals=0)
])

@app.callback(
    [Output('live-capital', 'children'),
     Output('live-profit', 'children'),
     Output('live-route', 'children'),
     Output('live-total-tri', 'children'),
     Output('live-speed', 'children'),
     Output('live-table', 'children')],
    [Input('interval-component', 'n_intervals')]
)
def update_dashboard(n):
    cap = f"${data_compartida['capital_actual']:.2f} USDT"
    
    val_profit = data_compartida['mejor_profit']
    color_prof = '#02c076' if val_profit >= MIN_PROFIT else '#f84960'
    prof = html.Span(f"{val_profit:.4f}%", style={'color': color_prof})
    
    ruta = data_compartida['mejor_ruta']
    total_tri = f"{data_compartida['total_triangulos']:,} rutas"
    velocidad = f"{data_compartida['tiempo_escaneo']:.2f}s"
    
    return cap, prof, ruta, total_tri, velocidad, data_compartida["transacciones_html"]

if __name__ == "__main__":
    # --- LA CORRECCIÓN CLAVE: Encendemos el motor del bot junto a la web ---
    hilo_bot = threading.Thread(target=bucle_bot_segundo)
    hilo_bot.daemon = True
    hilo_bot.start()
    
    app.run(host='0.0.0.0', port=8080, debug=False)

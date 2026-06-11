import time
import threading
import logging
import ccxt
from dash import Dash, html, dcc
from dash.dependencies import Input, Output

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger()

# Configuración del motor del bot
MIN_PROFIT = 0.3      
MAX_PROFIT = 5.0      
TAKER_FEE = 0.0010     
CAPITAL_SIMULADO = 50.0  

data_compartida = {
    "capital_actual": CAPITAL_SIMULADO,
    "mejor_ruta": "Escaneando OKX...",
    "mejor_profit": 0.0,
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
        
        while True:
            try:
                tickers = exchange.fetch_tickers()
                mejor_profit = -999.0
                mejor_ruta_texto = ""

                for tri in triangulos:
                    profit, texto = calcular_arbitraje(exchange, tri, tickers)
                    if profit > mejor_profit:
                        mejor_profit = profit
                        mejor_ruta_texto = texto

                # Si el spread supera el mínimo, se ejecuta la transacción
                if mejor_profit >= MIN_PROFIT:
                    ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                    CAPITAL_SIMULADO += ganancia
                    
                    nueva_tx = {
                        "Hora": time.strftime("%H:%M:%S"),
                        "Ruta": mejor_ruta_texto,
                        "Rendimiento": f"+{mejor_profit:.3f}%",
                        "Resultado": f"${CAPITAL_SIMULADO:.2f}"
                    }
                    data_compartida["transacciones"].insert(0, nueva_tx)
                    if len(data_compartida["transacciones"]) > 8:
                        data_compartida["transacciones"].pop()

                data_compartida["capital_actual"] = CAPITAL_SIMULADO
                data_compartida["mejor_ruta"] = mejor_ruta_texto
                data_compartida["mejor_profit"] = mejor_profit

            except Exception as e:
                logger.error(f"Error ciclo: {e}")
            time.sleep(1)

    except Exception as e:
        logger.error(f"Fallo crítico: {e}")

# --- DISEÑO DEL PANEL MÓVIL ESTILO EXCHANGE ---
app = Dash(__name__)

app.layout = html.Div(style={'backgroundColor': '#12161a', 'color': '#ffffff', 'fontFamily': 'sans-serif', 'padding': '12px', 'minHeight': '100vh'}, children=[
    html.H2("⚡ OKX ARBITRAGE PRO", style={'textAlign': 'center', 'color': '#eaecef', 'fontSize': '20px', 'letterSpacing': '1px', 'borderBottom': '1px solid #2b3139', 'paddingBottom': '10px'}),
    
    # Tarjeta de Balance
    html.Div(style={'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '20px', 'marginTop': '15px', 'boxShadow': '0px 4px 6px rgba(0,0,0,0.2)'}, children=[
        html.Div("Capital Simulado Disponible", style={'color': '#848e9c', 'fontSize': '14px', 'textAlign': 'center'}),
        html.Div(id="live-capital", style={'color': '#02c076', 'fontSize': '32px', 'fontWeight': 'bold', 'textAlign': 'center', 'marginTop': '5px'})
    ]),
    
    # Grid de Estado del Mercado
    html.Div(style={'display': 'flex', 'gap': '10px', 'marginTop': '15px'}, children=[
        html.Div(style={'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px', 'flex': '1', 'textAlign': 'center'}, children=[
            html.Div("Spread Máximo", style={'color': '#848e9c', 'fontSize': '13px'}),
            html.Div(id="live-profit", style={'fontSize': '20px', 'fontWeight': 'bold', 'marginTop': '5px'})
        ]),
        html.Div(style={'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px', 'flex': '1', 'textAlign': 'center'}, children=[
            html.Div("Filtro Mínimo", style={'color': '#848e9c', 'fontSize': '13px'}),
            html.Div(f"+{MIN_PROFIT}%", style={'color': '#f0b90b', 'fontSize': '20px', 'fontWeight': 'bold', 'marginTop': '5px'})
        ])
    ]),
    
    # Contenedor de Ruta Óptima
    html.Div(style={'marginTop': '15px', 'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px'}, children=[
        html.Div("Mejor Ruta Detectada (1s):", style={'color': '#848e9c', 'fontSize': '13px', 'marginBottom': '5px'}),
        html.Div(id="live-route", style={'color': '#f0b90b', 'fontSize': '18px', 'fontWeight': 'bold', 'textAlign': 'center', 'fontFamily': 'monospace'})
    ]),
    
    # Historial de trades en formato lista limpia
    html.Div(style={'marginTop': '20px', 'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px'}, children=[
        html.Div("📋 Registro de Operaciones Exitosas", style={'color': '#eaecef', 'fontSize': '15px', 'fontWeight': 'bold', 'borderBottom': '1px solid #2b3139', 'paddingBottom': '8px', 'marginBottom': '10px'}),
        html.Div(id="live-table")
    ]),
    
    dcc.Interval(id='interval-component', interval=1500, n_intervals=0)
])

@app.callback(
    [Output('live-capital', 'children'),
     Output('live-profit', 'children'),
     Output('live-route', 'children'),
     Output('live-table', 'children')],
    [Input('interval-component', 'n_intervals')]
)
def update_dashboard(n):
    cap = f"${data_compartida['capital_actual']:.4f}"
    
    # El color cambia a verde si el spread actual es rentable
    profit_actual = data_compartida['mejor_profit']
    color_profit = '#02c076' if profit_actual >= MIN_PROFIT else '#f84960'
    prof = html.Span(f"{profit_actual:.4f}%", style={'color': color_profit})
    
    ruta = data_compartida['mejor_ruta']
    
    # Formateo de lista de transacciones estilo bloque móvil
    tx_list = data_compartida["transacciones"]
    if not tx_list:
        lista_html = html.Div("Buscando ineficiencias en OKX...", style={'color': '#848e9c', 'textAlign': 'center', 'fontSize': '13px', 'padding': '15px'})
    else:
        lista_html = html.Div([
            html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'padding': '10px 0', 'borderBottom': '1px solid #2b3139', 'fontSize': '13px'}, children=[
                html.Span(tx["Hora"], style={'color': '#848e9c'}),
                html.Span(tx["Ruta"], style={'fontWeight': 'bold', 'color': '#eaecef'}),
                html.Span(tx["Rendimiento"], style={'color': '#02c076', 'fontWeight': 'bold'}),
                html.Span(tx["Resultado"], style={'color': '#ffffff'})
            ]) for tx in tx_list
        ])
        
    return cap, prof, ruta, lista_html

if __name__ == "__main__":
    hilo_bot = threading.Thread(target=bucle_bot_segundo)
    hilo_bot.daemon = True
    hilo_bot.start()
    app.run(host='0.0.0.0', port=8080, debug=False)

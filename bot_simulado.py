import time
import threading
import logging
import ccxt
from dash import Dash, html, dcc
from dash.dependencies import Input, Output

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger()

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
    "ultimos_spreads": [0.0] * 10,
    "transacciones_html": [html.P("Esperando ineficiencias...")]
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
                    
                    texto_tx = f"{time.strftime('%H:%M:%S')} | {mejor_ruta_texto} | +{mejor_profit:.2f}% | Total: ${CAPITAL_SIMULADO:.2f}"
                    registro_trades.insert(0, html.P(texto_tx))
                    if len(registro_trades) > 5:
                        registro_trades.pop()
                    data_compartida["transacciones_html"] = list(registro_trades)

                data_compartida["capital_actual"] = CAPITAL_SIMULADO
                data_compartida["mejor_ruta"] = mejor_ruta_texto
                data_compartida["mejor_profit"] = mejor_profit
                data_compartida["tiempo_escaneo"] = time.time() - t_inicio
                
                data_compartida["ultimos_spreads"].append(mejor_profit)
                if len(data_compartida["ultimos_spreads"]) > 10:
                    data_compartida["ultimos_spreads"].pop(0)

            except Exception as e:
                logger.error(f"Error ciclo: {e}")
            time.sleep(1)

    except Exception as e:
        logger.error(f"Fallo crítico: {e}")

# --- ENTORNO WEB ULTRA SEGURO ---
app = Dash(__name__)

app.layout = html.Div(children=[
    html.H2("OKX ARBITRAGE PRO"),
    html.Hr(),
    
    html.H3("CAPITAL DISPONIBLE:"),
    html.H1(id="live-capital"),
    html.Hr(),
    
    html.P("Spread Maximo Actual:"),
    html.H3(id="live-profit"),
    
    html.P("Filtro Minimo:"),
    html.H4(f"+{MIN_PROFIT}%"),
    html.Hr(),
    
    html.P("Mejor Ruta Detectada:"),
    html.H3(id="live-route"),
    html.Hr(),

    html.P("Rutas Escaneadas Simultaneas:"),
    html.H4(id="live-total-tri"),
    
    html.P("Velocidad de Respuesta API:"),
    html.H4(id="live-speed"),
    html.Hr(),
    
    html.H3("HISTORIAL DE OPERACIONES"),
    html.Div(id="live-table"),
    
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
    prof = f"{data_compartida['mejor_profit']:.4f}%"
    ruta = data_compartida['mejor_ruta']
    total_tri = f"{data_compartida['total_triangulos']:,} caminos en ejecucion"
    velocidad = f"{data_compartida['tiempo_escaneo']:.2f} segundos"
    
    return cap, prof, ruta, total_tri, velocidad, data_compartida["transacciones_html"]

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=False)

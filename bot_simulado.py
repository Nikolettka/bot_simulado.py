import time
import threading
import logging
import ccxt
import sys
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
    "total_triangulos": 0,
    "tiempo_escaneo": 0.0,
    "tamano_peticion_kb": 0.0,
    "total_datos_mb": 0.0,
    "record_max_profit": -999.0,
    "record_min_profit": 999.0,
    "top_rutas": [("N/A", 0.0), ("N/A", 0.0), ("N/A", 0.0)],
    "transacciones_html": [html.Div("Esperando oportunidades (>= 0.3%)...", style={'color': '#848e9c', 'textAlign': 'center', 'padding': '10px'})]
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
    acumulado_bytes = 0
    
    try:
        markets = exchange.load_markets()
        triangulos = buscar_todos_los_triangulos(markets)
        data_compartida["total_triangulos"] = len(triangulos)
        
        while True:
            try:
                t_inicio = time.time()
                tickers = exchange.fetch_tickers()
                
                # Calcular el peso de los datos recibidos de la API de OKX
                peso_bytes = sys.getsizeof(str(tickers))
                acumulado_bytes += peso_bytes
                data_compartida["tamano_peticion_kb"] = peso_bytes / 1024
                data_compartida["total_datos_mb"] = acumulado_bytes / (1024 * 1024)

                resultados_vuelta = []
                for tri in triangulos:
                    profit, texto = calcular_arbitraje(exchange, tri, tickers)
                    if profit > -50.0:  # Evita errores de tickers vacíos
                        resultados_vuelta.append((texto, profit))

                # Ordenar todos los caminos evaluados de mayor a menor beneficio
                resultados_vuelta.sort(key=lambda x: x[1], reverse=True)
                
                # Extraer el Top 3
                top_3 = resultados_vuelta[:3]
                while len(top_3) < 3: top_3.append(("N/A", 0.0))
                data_compartida["top_rutas"] = top_3

                mejor_ruta_texto, mejor_profit = top_3[0]

                # Récords históricos de la sesión
                if mejor_profit > data_compartida["record_max_profit"]:
                    data_compartida["record_max_profit"] = mejor_profit
                if mejor_profit < data_compartida["record_min_profit"] and mejor_profit > -10.0:
                    data_compartida["record_min_profit"] = mejor_profit

                # Ejecutar trade simulado si supera el spread requerido
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
                    if len(registro_trades) > 5: registro_trades.pop()
                    data_compartida["transacciones_html"] = list(registro_trades)

                data_compartida["capital_actual"] = CAPITAL_SIMULADO
                data_compartida["tiempo_escaneo"] = time.time() - t_inicio

            except Exception as e:
                logger.error(f"Error ciclo: {e}")
            time.sleep(1)

    except Exception as e:
        logger.error(f"Fallo critico: {e}")

# --- ENTORNO WEB EXPANDIDO MASIVO ---
app = Dash(__name__)

app.layout = html.Div(style={'backgroundColor': '#12161a', 'color': '#ffffff', 'fontFamily': 'sans-serif', 'padding': '15px', 'minHeight': '100vh'}, children=[
    html.H2("⚡ OKX ARBITRAGE ULTRA PRO", style={'textAlign': 'center', 'color': '#eaecef', 'borderBottom': '1px solid #2b3139', 'paddingBottom': '10px', 'margin': '0'}),
    
    # Bloque 1: Capital Formateado
    html.Div(style={'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '20px', 'marginTop': '15px', 'textAlign': 'center'}, children=[
        html.Div("Capital Simulado Disponible", style={'color': '#848e9c', 'fontSize': '14px'}),
        html.Div(id="live-capital", style={'color': '#02c076', 'fontSize': '36px', 'fontWeight': 'bold', 'marginTop': '5px'})
    ]),
    
    # Bloque 2: Filtros básicos
    html.Div(style={'display': 'flex', 'gap': '10px', 'marginTop': '15px'}, children=[
        html.Div(style={'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px', 'flex': '1', 'textAlign': 'center'}, children=[
            html.Div("Spread Máximo", style={'color': '#848e9c', 'fontSize': '13px'}),
            html.Div(id="live-profit", style={'fontSize': '20px', 'fontWeight': 'bold', 'marginTop': '5px'})
        ]),
        html.Div(style={'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px', 'flex': '1', 'textAlign': 'center'}, children=[
            html.Div("Filtro Operación", style={'color': '#848e9c', 'fontSize': '13px'}),
            html.Div(f"+{MIN_PROFIT}%", style={'color': '#f0b90b', 'fontSize': '20px', 'fontWeight': 'bold', 'marginTop': '5px'})
        ])
    ]),

    # NUEVO BLOQUE: TOP 3 RUTAS EN TIEMPO REAL
    html.Div(style={'marginTop': '15px', 'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px'}, children=[
        html.Div("🔥 Top 3 Caminos Más Rentables Libros OKX", style={'color': '#eaecef', 'fontSize': '14px', 'fontWeight': 'bold', 'borderBottom': '1px solid #2b3139', 'paddingBottom': '6px', 'marginBottom': '10px'}),
        html.Div(id="live-top-3-container")
    ]),

    # NUEVO BLOQUE: RENDIMIENTO DE LA SESIÓN (RÉCORDS)
    html.Div(style={'marginTop': '15px', 'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px'}, children=[
        html.Div("📊 Historial de Rangos de Profit (Sesión)", style={'color': '#eaecef', 'fontSize': '14px', 'fontWeight': 'bold', 'borderBottom': '1px solid #2b3139', 'paddingBottom': '6px', 'marginBottom': '10px'}),
        html.Div(style={'display': 'flex', 'justifyContent': 'space-between', 'fontSize': '13px'}, children=[
            html.Div([html.Span("Mejor Spread Visto: ", style={'color': '#848e9c'}), html.Span(id="live-record-max", style={'fontWeight': 'bold', 'color': '#02c076'})]),
            html.Div([html.Span("Peor Spread Visto: ", style={'color': '#848e9c'}), html.Span(id="live-record-min", style={'fontWeight': 'bold', 'color': '#f84960'})])
        ])
    ]),

    # Detalles Técnicos de Motor y Datos de Red
    html.Div(style={'marginTop': '15px', 'backgroundColor': '#1e232a', 'borderRadius': '12px', 'padding': '15px'}, children=[
        html.Div("⚙️ Telemetría del Sistema y Tráfico de Red", style={'color': '#eaecef', 'fontSize': '14px', 'fontWeight': 'bold', 'borderBottom': '1px solid #2b3139', 'paddingBottom': '6px', 'marginBottom': '10px'}),
        html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr', 'gap': '10px', 'fontSize': '12px'}, children=[
            html.Div([html.Span("Caminos Activos: ", style={'color': '#848e9c'}), html.Span(id="live-total-tri", style={'fontWeight': 'bold'})]),
            html.Div([html.Span("Latencia API: ", style={'color': '#848e9c'}), html.Span(id="live-speed", style={'fontWeight': 'bold'})]),

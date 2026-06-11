import time
import threading
import logging
import ccxt
import pandas as pd
from dash import Dash, html, dcc
from dash.dependencies import Input, Output
import plotly.graph_objs as go

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger()

# Parámetros del simulador agresivo
MIN_PROFIT = 0.3      
MAX_PROFIT = 5.0      
TAKER_FEE = 0.0010     
CAPITAL_SIMULADO = 50.0  

# Memoria global expandida para el Dashboard masivo
data_compartida = {
    "capital_actual": CAPITAL_SIMULADO,
    "mejor_ruta": "Escaneando OKX...",
    "mejor_profit": 0.0,
    "historial_balance": [50.0],  # Puntos para el gráfico de línea
    "tiempos": [time.strftime("%H:%M:%S")],
    "transacciones": []  # Registro de trades completados
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

                # Si hay ganancia simulada, se ejecuta la acción
                if mejor_profit >= MIN_PROFIT:
                    ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                    CAPITAL_SIMULADO += ganancia
                    
                    # Añadir al historial de transacciones visibles
                    nueva_tx = {
                        "Hora": time.strftime("%H:%M:%S"),
                        "Ruta": mejor_ruta_texto,
                        "Rendimiento": f"+{mejor_profit:.3f}%",
                        "Resultado": f"${CAPITAL_SIMULADO:.2f} USDT"
                    }
                    data_compartida["transacciones"].insert(0, nueva_tx)
                    if len(data_compartida["transacciones"]) > 10:
                        data_compartida["transacciones"].pop()

                # Guardar datos métricos continuos para la gráfica lineal
                data_compartida["capital_actual"] = CAPITAL_SIMULADO
                data_compartida["mejor_ruta"] = mejor_ruta_texto
                data_compartida["mejor_profit"] = mejor_profit
                
                data_compartida["historial_balance"].append(CAPITAL_SIMULADO)
                data_compartida["tiempos"].append(time.strftime("%H:%M:%S"))
                
                if len(data_compartida["historial_balance"]) > 50:
                    data_compartida["historial_balance"].pop(0)
                    data_compartida["tiempos"].pop(0)

            except Exception as e:
                logger.error(f"Error ciclo: {e}")
            time.sleep(1)

    except Exception as e:
        logger.error(f"Fallo crítico: {e}")

# --- ENTORNO WEB MASIVO ---
app = Dash(__name__)

app.layout = html.Div(style={'backgroundColor': '#0b0e11', 'color': '#eaecef', 'fontFamily': 'sans-serif', 'padding': '15px'}, children=[
    html.H1("⚡ OKX PRO ARBITRAGE", style={'textAlign': 'center', 'color': '#f0b90b', 'fontSize': '26px'}),
    
    # Tarjetas principales
    html.Div(style={'display': 'flex', 'gap': '10px', 'marginTop': '15px'}, children=[
        html.Div(style={'backgroundColor': '#1e2329', 'padding': '15px', 'borderRadius': '8px', 'flex': '1', 'textAlign': 'center'}, children=[
            html.Span("Capital Disponible", style={'color': '#848e9c', 'fontSize': '12px'}),
            html.H2(id="live-capital", style={'color': '#02c076', 'fontSize': '20px', 'marginTop': '5px'})
        ]),
        html.Div(style={'backgroundColor': '#1e2329', 'padding': '15px', 'borderRadius': '8px', 'flex': '1', 'textAlign': 'center'}, children=[
            html.Span("Spread Máximo", style={'color': '#848e9c', 'fontSize': '12px'}),
            html.H2(id="live-profit", style={'color': '#f84960', 'fontSize': '20px', 'marginTop': '5px'})
        ])
    ]),
    
    # Ruta en tiempo real
    html.Div(style={'marginTop': '15px', 'backgroundColor': '#1e2329', 'padding': '15px', 'borderRadius': '8px'}, children=[
        html.Span("Cadena Evaluada Óptima:", style={'color': '#848e9c', 'fontSize': '12px'}),
        html.H3(id="live-route", style={'color': '#f0b90b', 'marginTop': '5px', 'fontSize': '18px', 'textAlign': 'center'})
    ]),
    
    # Gráfica del capital interactiva
    html.Div(style={'marginTop': '20px', 'backgroundColor': '#1e2329', 'borderRadius': '8px', 'padding': '10px'}, children=[
        html.H4("Evolución del Balance ($)", style={'paddingLeft': '10px', 'color': '#eaecef'}),
        dcc.Graph(id="live-graph", config={'displayModeBar': False}, style={'height': '220px'})
    ]),
    
    # Tabla de Órdenes Ejecutadas
    html.Div(style={'marginTop': '20px', 'backgroundColor': '#1e2329', 'borderRadius': '8px', 'padding': '15px'}, children=[
        html.H4("📜 Últimas Operaciones Ejecutadas (Simuladas)", style={'color': '#f0b90b', 'marginBottom': '10px'}),
        html.Div(id="live-table", style={'overflowX': 'auto'})
    ]),
    
    dcc.Interval(id='interval-component', interval=1500, n_intervals=0)
])

@app.callback(
    [Output('live-capital', 'children'),
     Output('live-profit', 'children'),
     Output('live-route', 'children'),
     Output('live-graph', 'figure'),
     Output('live-table', 'children')],
    [Input('interval-component', 'n_intervals')]
)
def update_dashboard(n):
    cap = f"${data_compartida['capital_actual']:.4f} USDT"
    prof = f"{data_compartida['mejor_profit']:.4f}%"
    ruta = data_compartida['mejor_ruta']
    
    # Renderizado de gráfico lineal
    fig = go.Figure(data=[go.Scatter(
        x=data_compartida["tiempos"],
        y=data_compartida["historial_balance"],
        mode='lines+markers',
        line=dict(color='#02c076', width=2),
        marker=dict(size=4, color='#f0b90b')
    )])
    fig.update_layout(
        margin=dict(l=40, r=10, t=10, b=35),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False, tickcolor='#848e9c', font=dict(color='#848e9c', size=10)),
        yaxis=dict(showgrid=True, gridcolor='#2b3139', tickcolor='#848e9c', font=dict(color='#848e9c', size=10))
    )
    
    # Construcción de la tabla de registros en HTML
    tx_list = data_compartida["transacciones"]
    if not tx_list:
        tabla_html = html.Div("Esperando ineficiencias de mercado (≥ 0.3%)...", style={'color': '#848e9c', 'textAlign': 'center', 'fontSize': '13px', 'padding': '10px'})
    else:
        rows = [
            html.Tr([
                html.Td(tx["Hora"], style={'padding': '8px', 'borderBottom': '1px solid #2b3139'}),
                html.Td(tx["Ruta"], style={'padding': '8px', 'borderBottom': '1px solid #2b3139'}),
                html.Td(tx["Rendimiento"], style={'padding': '8px', 'borderBottom': '1px solid #2b3139', 'color': '#02c076'}),
                html.Td(tx["Resultado"], style={'padding': '8px', 'borderBottom': '1px solid #2b3139'})
            ]) for tx in tx_list
        ]
        tabla_html = html.Table(
            [html.Tr([html.Th("Hora"), html.Th("Ruta"), html.Th("Prof"), html.Th("Total")], style={'textAlign': 'left', 'color': '#848e9c', 'fontSize': '12px'})] + rows,
            style={'width': '100%', 'fontSize': '13px', 'borderCollapse': 'collapse'}
        )
        
    return cap, prof, ruta, fig, tabla_html

if __name__ == "__main__":
    hilo_bot = threading.Thread(target=bucle_bot_segundo)
    hilo_bot.daemon = True
    hilo_bot.start()
    app.run(host='0.0.0.0', port=8080, debug=False)

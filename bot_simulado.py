import time
import threading
import logging
import ccxt
import sys
from flask import Flask, render_template_string, redirect, url_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger()

MIN_PROFIT = 0.3      
MAX_PROFIT = 5.0      
TAKER_FEE = 0.0010     
CAPITAL_SIMULADO = 50.0  

# Interruptor de control global
BOT_ENCENDIDO = True

data_compartida = {
    "capital_actual": CAPITAL_SIMULADO,
    "total_triangulos": 0,
    "tiempo_escaneo": 0.0,
    "tamano_peticion_kb": 0.0,
    "total_datos_mb": 0.0,
    "record_max_profit": 0.0,
    "record_min_profit": 0.0,
    "mejor_ruta": "N/A",
    "mejor_profit": 0.0,
    "top_rutas_texto": "Cargando...",
    "transacciones_texto": "Esperando oportunidades (>= 0.3%)..."
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
            secuencia_texto += base
            moneda_actual = base
        else:
            monto = (monto * ticker['bid']) * (1 - TAKER_FEE)
            secuencia_texto += quote
            moneda_actual = quote
        if i < 2: secuencia_texto += ">"

    return (monto - 1.0) * 100, secuencia_texto

def bucle_bot_segundo():
    global CAPITAL_SIMULADO, BOT_ENCENDIDO
    exchange = inicializar_okx_publico()
    registro_trades = []
    acumulado_bytes = 0
    
    try:
        markets = exchange.load_markets()
        triangulos = buscar_todos_los_triangulos(markets)
        data_compartida["total_triangulos"] = len(triangulos)
        
        while True:
            # Si el interruptor está apagado, el bot duerme y no consulta la API
            if not BOT_ENCENDIDO:
                data_compartida["mejor_ruta"] = "BOT DETENIDO / PAUSADO"
                data_compartida["mejor_profit"] = 0.0
                data_compartida["top_rutas_texto"] = "<p style='color:gray;'>Sistema en pausa por el usuario.</p>"
                time.sleep(1)
                continue
                
            try:
                t_inicio = time.time()
                tickers = exchange.fetch_tickers()
                
                peso_bytes = sys.getsizeof(str(tickers))
                acumulado_bytes += peso_bytes
                data_compartida["tamano_peticion_kb"] = peso_bytes / 1024
                data_compartida["total_datos_mb"] = acumulado_bytes / (1024 * 1024)

                resultados_vuelta = []
                for tri in triangulos:
                    profit, texto = calcular_arbitraje(exchange, tri, tickers)
                    if profit > -50.0:
                        resultados_vuelta.append((texto, profit))

                resultados_vuelta.sort(key=lambda x: x[1], reverse=True)
                top_3 = resultados_vuelta[:3]
                
                top_html = ""
                for i, r in enumerate(top_3):
                    color = "green" if r[1] >= MIN_PROFIT else "red"
                    top_html += f"<p>#{i+1} {r[0]} -> <b style='color:{color};'>{r[1]:.4f}%</b></p>"
                data_compartida["top_rutas_texto"] = top_html

                if top_3:
                    mejor_ruta_texto, mejor_profit = top_3[0]
                else:
                    mejor_ruta_texto, mejor_profit = "N/A", 0.0
                    
                data_compartida["mejor_ruta"] = mejor_ruta_texto
                data_compartida["mejor_profit"] = mejor_profit

                if mejor_profit > data_compartida["record_max_profit"]:
                    data_compartida["record_max_profit"] = mejor_profit
                if mejor_profit < data_compartida["record_min_profit"] and mejor_profit > -10.0:
                    data_compartida["record_min_profit"] = mejor_profit

                if mejor_profit >= MIN_PROFIT:
                    ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                    CAPITAL_SIMULADO += ganancia
                    
                    tx_linea = f"<p><span style='color:gray;'>{time.strftime('%H:%M:%S')}</span> | <b>{mejor_ruta_texto}</b> | <b style='color:green;'>+{mejor_profit:.2f}%</b> | <b>${CAPITAL_SIMULADO:.2f}</b></p>"
                    registro_trades.insert(0, tx_linea)
                    if len(registro_trades) > 5: registro_trades.pop()
                    data_compartida["transacciones_texto"] = "".join(registro_trades)

                data_compartida["capital_actual"] = CAPITAL_SIMULADO
                data_compartida["tiempo_escaneo"] = time.time() - t_inicio

            except Exception as e:
                logger.error(f"Error ciclo: {e}")
            time.sleep(1)

    except Exception as e:
        logger.error(f"Fallo critico: {e}")

app = Flask(__name__)

# Diseño web con botones interactivos inyectados
html_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset='utf-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>OKX ARBITRAGE PRO</title>
    <meta http-equiv='refresh' content='1'>
</head>
<body style='background-color: #12161a; color: #ffffff; font-family: sans-serif; padding: 15px;'>
    <h2 style='text-align:center; color:#eaecef; border-bottom:1px solid #2b3139; padding-bottom:10px;'>⚡ OKX ARBITRAGE ULTRA PRO</h2>
    
    <!-- PANEL DE CONTROL ON/OFF -->
    <div style='background-color: #1e232a; border-radius: 12px; padding: 15px; text-align: center;'>
        <p style='margin: 0 0 10px 0; color:#848e9c; font-size:13px;'>Estado del Motor Principal</p>
        <span style='background-color: {{ color_estado }}; padding: 6px 12px; border-radius: 20px; font-weight: bold; font-size: 14px;'>{{ texto_estado }}</span>
        <div style='margin-top: 15px;'>
            <a href='/toggle' style='text-decoration: none; background-color: {{ color_boton }}; color: white; padding: 10px 25px; border-radius: 8px; font-weight: bold; font-size: 15px; display: inline-block;'>{{ texto_boton }} MOTOR</a>
        </div>
    </div>

    <div style='background-color: #1e232a; border-radius: 12px; padding: 15px; margin-top: 15px; text-align: center;'>
        <p style='color: #848e9c; margin: 0;'>Capital Simulado Disponible</p>
        <h1 style='color:#02c076; margin: 5px 0;'>${{ "%.2f"|format(capital) }} USDT</h1>
    </div>
    
    <div style='background-color: #1e232a; border-radius: 12px; padding: 15px; margin-top: 15px;'>
        <p style='margin: 5px 0;'>Spread Maximo Actual: <b style='color:{{ color_p }};'>{{ "%.4f"|format(profit) }}%</b></p>
        <p style='margin: 5px 0;'>Filtro Minimo Operacion: <b style='color:#f0b90b;'>+{{ min_p }}%</b></p>
    </div>

    <div style='background-color: #1e232a; border-radius: 12px; padding: 15px; margin-top: 15px;'>
        <h4 style='color:#eaecef; margin: 0 0 10px 0;'>🔥 Top 3 Caminos Mas Rentables OKX</h4>
        {{ top_3|safe }}
    </div>

    <div style='background-color: #1e232a; border-radius: 12px; padding: 15px; margin-top: 15px;'>
        <h4 style='color:#eaecef; margin: 0 0 10px 0;'>📊 Historial de Rangos (Sesion)</h4>
        <p style='margin: 5px 0;'>Max Spread Visto: <b style='color:green;'>{{ "%.4f"|format(r_max) }}%</b></p>
        <p style='margin: 5px 0;'>Min Spread Visto: <b style='color:red;'>{{ "%.4f"|format(r_min) }}%</b></p>
    </div>

    <div style='background-color: #1e232a; border-radius: 12px; padding: 15px; margin-top: 15px;'>
        <h4 style='color:#eaecef; margin: 0 0 10px 0;'>⚙️ Telemetria и Trafico de Red</h4>
        <p style='margin: 3px 0;'>Rutas en ejecucion: <b>{{ "{:,}".format(rutas) }}</b></p>
        <p style='margin: 3px 0;'>Latencia Escaneo: <b>{{ "%.2f"|format(latencia) }}s</b></p>
        <p style='margin: 3px 0;'>Peso Peticion API: <b>{{ "%.1f"|format(peso) }} KB</b></p>
        <p style='margin: 3px 0;'>Total Red Descargado: <b>{{ "%.2f"|format(total_r) }} MB</b></p>
    </div>

    <div style='background-color: #1e232a; border-radius: 12px; padding: 15px; margin-top: 15px;'>
        <h4 style='color:#eaecef; margin: 0 0 10px 0; border-bottom:1px solid #2b3139; padding-bottom:5px;'>📜 Registro de Operaciones Exitosas</h4>
        {{ trades|safe }}
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    color_profit = "#02c076" if data_compartida['mejor_profit'] >= MIN_PROFIT else "#f84960"
    
    # Parámetros visuales del botón e indicador

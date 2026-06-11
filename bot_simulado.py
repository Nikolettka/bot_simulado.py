import time
import threading
import logging
import ccxt
import sys
from flask import Flask

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger()

MIN_PROFIT = 0.3      
MAX_PROFIT = 5.0      
TAKER_FEE = 0.0010     
CAPITAL_SIMULADO = 50.0  

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
    "top_rutas_texto": "Cargando datos...",
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
            if not BOT_ENCENDIDO:
                data_compartida["mejor_ruta"] = "MOTOR INTERRUMPIDO"
                data_compartida["mejor_profit"] = 0.0
                data_compartida["top_rutas_texto"] = "<p style='color:gray;'>Bot pausado por el usuario.</p>"
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
                    color = "#02c076" if r[1] >= MIN_PROFIT else "#f84960"
                    top_html += f"<div style='display:flex;justify-content:space-between;padding:6px 0;font-family:monospace;font-size:14px;border-bottom:1px solid #2b3139;'><span>#{i+1} {r[0]}</span><span style='color:{color};font-weight:bold;'>{r[1]:.4f}%</span></div>"
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
                    
                    tx_linea = f"<div style='display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2b3139;font-size:13px;'><span style='color:#848e9c;'>{time.strftime('%H:%M:%S')}</span><span style='font-weight:bold;'>{mejor_ruta_texto}</span><span style='color:#02c076;font-weight:bold;'>+{mejor_profit:.2f}%</span><span style='font-weight:bold;'>${CAPITAL_SIMULADO:.2f}</span></div>"
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

# Diseño plano sin etiquetas anidadas de entornos web complejos
html_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset='utf-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>OKX ARBITRAGE PRO</title>
    <script>
        setInterval(function(){{ window.location.reload(); }}, 1200);
    </script>
    <style>
        body {{ background-color: #12161a; color: #ffffff; font-family: sans-serif; padding: 12px; margin: 0; }}
        .card {{ background-color: #1e232a; border-radius: 12px; padding: 15px; margin-top: 12px; }}
        .grid {{ display: flex; gap: 10px; margin-top: 12px; }}
        .col {{ flex: 1; background-color: #1e232a; border-radius: 12px; padding: 12px; text-align: center; }}
        .label {{ color: #848e9c; font-size: 12px; }}
        .value {{ font-size: 18px; font-weight: bold; margin-top: 4px; }}
        .btn {{ display: inline-block; background-color: %s; color: white; padding: 10px 30px; border-radius: 8px; font-weight: bold; text-decoration: none; margin-top: 10px; }}
    </style>
</head>
<body>
    <h2 style='text-align:center;color:#eaecef;border-bottom:1px solid #2b3139;padding-bottom:10px;margin:0;'>⚡ OKX ARBITRAGE ULTRA PRO</h2>
    
    <!-- CONTROL DE INTERRUPTOR VISIBLE -->
    <div class='card' style='text-align:center;'>
        <div class='label'>Estado del Sistema</div>
        <div style='font-size:16px; font-weight:bold; margin-top:5px; color:%s;'>%s</div>
        <a class='btn' href='/toggle'>%s MOTOR</a>
    </div>

    <div class='card' style='text-align:center;'>
        <div class='label'>Capital Simulado Disponible</div>
        <div style='color:#02c076;font-size:34px;font-weight:bold;margin-top:5px;'>$%s USDT</div>
    </div>
    
    <div class='grid'>
        <div class='col'>
            <div class='label'>Spread Maximo</div>
            <div class='value' style='color:%s;'>%s%%</div>
        </div>
        <div class='col'>
            <div class='label'>Filtro Minimo</div>
            <div class='value' style='color:#f0b90b;'>+%s%%</div>
        </div>
    </div>

    <div class='card'>
        <div class='label' style='margin-bottom:8px;font-weight:bold;color:#eaecef;'>🔥 Top 3 Caminos Mas Rentables OKX</div>
        %s
    </div>

    <div class='card'>
        <div class='label' style='margin-bottom:6px;font-weight:bold;color:#eaecef;'>📊 Historial de Rangos (Sesion)</div>
        <div style='display:flex;justify-content:space-between;font-size:13px;'>
            <div><span class='label'>Max Spread:</span> <b style='color:#02c076;'>%s%%</b></div>
            <div><span class='label'>Min Spread:</span> <b style='color:#f84960;'>%s%%</b></div>
        </div>
    </div>

    <div class='card'>
        <div class='label' style='margin-bottom:8px;font-weight:bold;color:#eaecef;'>⚙️ Telemetria и Trafico de Red</div>
        <div style='font-size:12px; display:grid; grid-template-columns:1fr 1fr; gap:6px;'>
            <div><span class='label'>Rutas:</span> <b>%s</b></div>
            <div><span class='label'>Latencia:</span> <b>%s s</b></div>
            <div><span class='label'>Peso API:</span> <b>%s KB</b></div>
            <div><span class='label'>Total Red:</span> <b>%s MB</b></div>
        </div>
    </div>

    <div class='card'>

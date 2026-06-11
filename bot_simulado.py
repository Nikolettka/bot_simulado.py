import time
import threading
import logging
import ccxt
import sys
import os
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

                resultados_vuelta.sort(key=lambda x: x, reverse=True)
                top_3 = resultados_vuelta[:3]
                
                top_html = ""
                for i, r in enumerate(top_3):
                    color = "#02c076" if r >= MIN_PROFIT else "#f84960"
                    top_html += f"<div style='display:flex;justify-content:space-between;padding:6px 0;font-family:monospace;font-size:14px;border-bottom:1px solid #2b3139;'><span>#{i+1} {r}</span><span style='color:{color};font-weight:bold;'>{r:.4f}%</span></div>"
                data_compartida["top_rutas_texto"] = top_html

                if top_3:
                    mejor_ruta_texto, mejor_profit = top_3
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

@app.route('/')
def home():
    color_profit = "#02c076" if data_compartida['mejor_profit'] >= MIN_PROFIT else "#f84960"
    c_btn = "#f84960" if BOT_ENCENDIDO else "#02c076"
    c_est = "#02c076" if BOT_ENCENDIDO else "#f84960"
    t_est = "SISTEMA ACTIVO / CORRIENDO" if BOT_ENCENDIDO else "SISTEMA DETENIDO / EN PAUSA"
    t_btn = "APAGAR" if BOT_ENCENDIDO else "ENCENDER"

    try:
        # Прочитане на изнесения външен HTML шаблон
        with open('index.html', 'r', encoding='utf-8') as f:
            html_template = f.read()
    except Exception:
        return "Error cargando index.html"

    return html_template % (
        c_btn, c_est, t_est, t_btn,
        f"{data_compartida['capital_actual']:.2f}",
        color_profit, f"{data_compartida['mejor_profit']:.4f}", f"{MIN_PROFIT:.1f}",
        data_compartida['top_rutas_texto'],
        f"{data_compartida['record_max_profit']:.4f}", f"{data_compartida['record_min_profit']:.4f}",
        f"{data_compartida['total_triangulos']:,}",
        f"{data_compartida['tiempo_escaneo']:.2f}", f"{data_compartida['tamano_peticion_kb']:.1f}", f"{data_compartida['total_datos_mb']:.2f}",
        data_compartida['transacciones_texto']
    )

@app.route('/toggle')
def toggle_bot():
    global BOT_ENCENDIDO
    BOT_ENCENDIDO = not BOT_ENCENDIDO
    return "<html><head><script>window.location.href='/';</script></head><body></body></html>"

if __name__ == "__main__":
    hilo_bot = threading.Thread(target=bucle_bot_segundo)
    hilo_bot.daemon = True
    hilo_bot.start()
    app.run(host='0.0.0.0', port=8080, debug=False)

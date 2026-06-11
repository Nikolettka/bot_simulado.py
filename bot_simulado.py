import time
import threading
import logging
import ccxt
import sys
from flask import Flask, render_template_string
from flask_socketio import SocketIO

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger()

MIN_PROFIT = 0.3      
MAX_PROFIT = 5.0      
TAKER_FEE = 0.0010     
CAPITAL_INICIAL = 50.0
CAPITAL_SIMULADO = 50.0  

BOT_ENCENDIDO = True
CONEXION_OKX = "🟢 Conectado"
TOTAL_TRADES = 0

data_compartida = {
    "capital_actual": CAPITAL_SIMULADO,
    "neto_ganado": 0.0,
    "total_triangulos": 0,
    "tiempo_escaneo": 0.0,
    "tamano_peticion_kb": 0.0,
    "total_datos_mb": 0.0,
    "record_max_profit": 0.0,
    "record_min_profit": 0.0,
    "top_rutas_texto": "Cargando rutas...",
    "transacciones_texto": "Esperando oportunidades (>= 0.3%)...",
    "ultima_hora": "00:00:00"
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
    detalles_precios = []

    for i, par in enumerate(triangulo):
        ticker = tickers.get(par)
        if not ticker or not ticker['ask'] or not ticker['bid']: return -999.0, "", []
        base, quote = par.split('/')

        if moneda_actual == quote:
            precio = ticker['ask']
            monto = (monto / precio) * (1 - TAKER_FEE)
            secuencia_texto += base
            moneda_actual = base
        else:
            precio = ticker['bid']
            monto = (monto * precio) * (1 - TAKER_FEE)
            secuencia_texto += quote
            moneda_actual = quote
        
        detalles_precios.append(f"{par}:{precio}")
        if i < 2: secuencia_texto += ">"

    return (monto - 1.0) * 100, secuencia_texto, detalles_precios

def bucle_bot_segundo(socketio_instance):
    global CAPITAL_SIMULADO, BOT_ENCENDIDO, CONEXION_OKX, TOTAL_TRADES
    exchange = inicializar_okx_publico()
    registro_trades = []
    acumulado_bytes = 0
    
    try:
        markets = exchange.load_markets()
        triangulos = buscar_todos_los_triangulos(markets)
        data_compartida["total_triangulos"] = len(triangulos)
        CONEXION_OKX = "🟢 Activa"
    except Exception:
        CONEXION_OKX = "🔴 Error de Red"
        return

    while True:
        if not BOT_ENCENDIDO:
            data_compartida["top_rutas_texto"] = "<div style='color:gray;text-align:center;'>Bot en pausa.</div>"
            socketio_instance.emit('update_data', obtener_payload_datos())
            time.sleep(2)
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
                profit, texto, precios = calcular_arbitraje(exchange, tri, tickers)
                if profit > -50.0:
                    resultados_vuelta.append((texto, profit, precios))

            resultados_vuelta.sort(key=lambda x: x[1], reverse=True)
            top_3 = resultados_vuelta[:3]
            
            top_html = ""
            for i, (r, p, prc) in enumerate(top_3):
                color = "#02c076" if p >= MIN_PROFIT else "#f84960"
                detalles_tokens = " | ".join(prc)
                top_html += f"<div style='padding:8px 0; border-bottom:1px solid #2b3139; font-size:13px;'><div style='display:flex;justify-content:space-between;'><span>#{i+1} <b>{r}</b></span><span style='color:{color};font-weight:bold;'>{p:.4f}%</span></div><div style='color:#848e9c; font-size:10px; font-family:monospace; margin-top:2px;'>{detalles_tokens}</div></div>"
            data_compartida["top_rutas_texto"] = top_html

            mejor_ruta_texto, mejor_profit, _ = top_3 if top_3 else ("N/A", 0.0, [])

            if mejor_profit > data_compartida["record_max_profit"]:
                data_compartida["record_max_profit"] = mejor_profit
            if mejor_profit < data_compartida["record_min_profit"] and mejor_profit > -10.0:
                data_compartida["record_min_profit"] = mejor_profit

            if mejor_profit >= MIN_PROFIT:
                TOTAL_TRADES += 1
                ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                CAPITAL_SIMULADO += ganancia
                
                tx_linea = f"<div style='display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2b3139;font-size:13px;'><span style='color:#848e9c;'>{time.strftime('%H:%M:%S')}</span><span style='font-weight:bold;'>{mejor_ruta_texto}</span><span style='color:#02c076;font-weight:bold;'>+{mejor_profit:.2f}%</span><span style='font-weight:bold;'>${CAPITAL_SIMULADO:.2f}</span></div>"
                registro_trades.insert(0, tx_linea)
                if len(registro_trades) > 5: registro_trades.pop()
                data_compartida["transacciones_texto"] = "".join(registro_trades)

            data_compartida["capital_actual"] = CAPITAL_SIMULADO
            data_compartida["neto_ganado"] = CAPITAL_SIMULADO - CAPITAL_INICIAL
            data_compartida["mejor_profit"] = mejor_profit
            data_compartida["mejor_ruta"] = mejor_ruta_texto
            data_compartida["tiempo_escaneo"] = time.time() - t_inicio
            data_compartida["ultima_hora"] = time.strftime("%H:%M:%S")

            socketio_instance.emit('update_data', obtener_payload_datos())

        except Exception as e:
            logger.error(f"Error ciclo: {e}")
            
        time.sleep(3)

def obtener_payload_datos():
    color_profit = "#02c076" if data_compartida['mejor_profit'] >= MIN_PROFIT else "#f84960"
    comision_estimada = CAPITAL_SIMULADO * 0.0030
    
    return {
        "capital": f"${data_compartida['capital_actual']:.2f} USDT",
        "neto": f"+${data_compartida['neto_ganado']:.4f} USDT",
        "trades": str(TOTAL_TRADES),
        "conexion": CONEXION_OKX,
        "color_p": color_profit,
        "profit": f"{data_compartida['mejor_profit']:.4f}%",
        "min_p": f"+{MIN_PROFIT}%",
        "comision": f"${comision_estimada:.4f} USDT",
        "top_3": data_compartida["top_rutas_texto"],
        "r_max": f"{data_compartida['record_max_profit']:.4f}%",
        "r_min": f"{data_compartida['record_min_profit']:.4f}%",
        "rutas": f"{data_compartida['total_triangulos']:,}",
        "latencia": f"{data_compartida['tiempo_escaneo']:.2f}s",
        "peso": f"{data_compartida['tamano_peticion_kb']:.1f} KB",
        "total_r": f"{data_compartida['total_datos_mb']:.2f} MB",
        "trades_lista": data_compartida["transacciones_texto"],
        "hora": data_compartida["ultima_hora"],
        "btn_texto": "APAGAR" if BOT_ENCENDIDO else "ENCENDER",
        "btn_color": "#f84960" if BOT_ENCENDIDO else "#02c076",
        "est_texto": "SISTEMA ACTIVO / CORRIENDO" if BOT_ENCENDIDO else "SISTEMA DETENIDO / EN PAUSA",
        "est_color": "#02c076" if BOT_ENCENDIDO else "#f84960"
    }

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/')
def home():
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            return render_template_string(f.read())
    except Exception:
        return "Error crítico cargando archivo index.html"

@app.route('/toggle')
def toggle_bot():
    global BOT_ENCENDIDO
    BOT_ENCENDIDO = not BOT_ENCENDIDO
    return "", 204

if __name__ == "__main__":
    hilo_bot = threading.Thread(target=bucle_bot_segundo, args=(socketio,))
    hilo_bot.daemon = True
    hilo_bot.start()
    # Ejecución forzada compatible con Railway y WebSockets masivos
    socketio.run(app, host='0.0.0.0', port=8080, debug=False, allow_unsafe_werkzeug=True)

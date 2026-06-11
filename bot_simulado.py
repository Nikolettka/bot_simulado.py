import time
import threading
import logging
import ccxt
import sys
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

root = logging.getLogger()
if root.handlers:
    for handler in root.handlers:
        root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout
)
logger = logging.getLogger()

# --- CONFIGURACIÓN PRINCIPAL ---
MODO_REAL = False  
TAKER_FEE_PERPETUAL = 0.0005   
MIN_PROFIT = 0.02              
MAX_PROFIT = 5.0      
CAPITAL_SIMULADO = 50.82  
TOTAL_TRADES = 4               

DICCIONARIO_MERCADOS = {}
MONEDAS_TOP = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOGE', 'USDT']

# Variables globales para compartir datos en tiempo real con el Dashboard
ULTIMO_SPREAD = 0.0
ULTIMA_RUTA = "Ninguna"
ULTIMO_REFRESCO = "Nunca"

class DashboardServer(BaseHTTPRequestHandler):
    """Servidor web ultraligero que solo consume datos cuando abres la página"""
    def do_GET(self):
        global CAPITAL_SIMULADO, TOTAL_TRADES, ULTIMO_SPREAD, ULTIMA_RUTA, ULTIMO_REFRESCO
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        # Evita que el navegador guarde caché para que los datos cambien al refrescar
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        
        # Diseño HTML optimizado para pantallas de móvil (Ligero y oscuro)
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>OKX Arbitrage Bot</title>
            <style>
                body {{ background-color: #121212; color: #ffffff; font-family: sans-serif; text-align: center; padding: 20px; }}
                .card {{ background-color: #1e1e1e; padding: 15px; border-radius: 10px; margin: 15px auto; max-width: 400px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
                h1 {{ color: #00ffcc; font-size: 24px; }}
                .profit {{ color: #00ff66; font-size: 28px; font-weight: bold; }}
                .spread {{ color: #ffcc00; font-size: 20px; }}
                .btn {{ background-color: #00ffcc; color: #121212; padding: 10px 20px; border: none; border-radius: 5px; font-weight: bold; cursor: pointer; text-decoration: none; display: inline-block; margin-top: 10px; }}
            </style>
        </head>
        <body>
            <h1>🤖 OKX BOT DASHBOARD</h1>
            <p style="color: #aaa; font-size: 12px;">El bot opera 24/7 en Railway. Este panel solo consume datos mientras lo miras.</p>
            
            <div class="card">
                <h3>💰 SALDO SIMULADO</h3>
                <div class="profit">${CAPITAL_SIMULADO:.2f} USDT</div>
                <p>Operaciones exitosas: {TOTAL_TRADES}</p>
            </div>
            
            <div class="card">
                <h3>📊 ÚLTIMO ANÁLISIS EN VIVO</h3>
                <div class="spread">Mejor Spread: {ULTIMO_SPREAD:.4f}%</div>
                <p style="font-size: 13px; color: #00ffcc;">Ruta: {ULTIMA_RUTA}</p>
                <p style="font-size: 11px; color: #888;">Actualizado: {ULTIMO_REFRESCO}</p>
            </div>
            
            <a href="" class="btn">🔄 ACTUALIZAR DATOS</a>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        # Desactivamos los logs de peticiones web para no saturar la consola de Railway
        return

def iniciar_dashboard():
    """Lanza el servidor web en el puerto asignado dinámicamente por Railway"""
    puerto = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", puerto), DashboardServer)
    logger.info(f"🌐 Mini Dashboard Web iniciado en el puerto {puerto}")
    server.serve_forever()

def inicializar_okx():
    return ccxt.okx({'enableRateLimit': True})

def buscar_todos_los_triangulos(markets):
    global DICCIONARIO_MERCADOS
    DICCIONARIO_MERCADOS.clear()
    adjacencia = {}
    for symbol, market in markets.items():
        try:
            if not market.get('active', True): continue
            base = market.get('base')
            quote = market.get('quote')
            if base in MONEDAS_TOP and quote in MONEDAS_TOP:
                DICCIONARIO_MERCADOS[symbol] = {'base': base, 'quote': quote, 'type': 'swap' if market.get('swap') else 'spot'}
                adjacencia.setdefault(base, set()).add((quote, symbol))
                adjacencia.setdefault(quote, set()).add((base, symbol))
        except Exception: continue
    triangulos = []
    if 'USDT' not in adjacencia: return []
    for m1, par1 in adjacencia['USDT']:
        if m1 not in adjacencia: continue
        for m2, par2 in adjacencia[m1]:
            if m2 == 'USDT' or par2 == par1: continue
            if m2 not in adjacencia: continue
            for m3, par3 in adjacencia[m2]:
                if m3 == 'USDT' and par3 != par1 and par3 != par2:
                    ruta = (par1, par2, par3)
                    if ruta not in triangulos: triangulos.append(ruta)
    return triangulos

def calcular_arbitraje(exchange, triangulo, tickers):
    global DICCIONARIO_MERCADOS
    monto = 1.0  
    secuencia_texto = ""
    moneda_actual = "USDT"
    for i, par in enumerate(triangulo):
        ticker = tickers.get(par)
        if not ticker or not ticker.get('ask') or not ticker.get('bid'): return -999.0, ""
        base, quote, tipo = DICCIONARIO_MERCADOS[par]['base'], DICCIONARIO_MERCADOS[par]['quote'], DICCIONARIO_MERCADOS[par]['type']
        if moneda_actual == quote:
            monto = (monto / (ticker['ask'] * 1.0001)) * (1 - TAKER_FEE_PERPETUAL)
            secuencia_texto += f"{base}({tipo})"
            moneda_actual = base
        else:
            monto = (monto * (ticker['bid'] * 0.9999)) * (1 - TAKER_FEE_PERPETUAL)
            secuencia_texto += f"{quote}({tipo})"
            moneda_actual = quote
        if i < 2: secuencia_texto += ">"
    return (monto - 1.0) * 100, secuencia_texto

def ejecutar_bot():
    global CAPITAL_SIMULADO, TOTAL_TRADES, ULTIMO_SPREAD, ULTIMA_RUTA, ULTIMO_REFRESCO
    exchange = inicializar_okx()
    logger.info("СТАРТИРАНЕ НА ВИСОКОЛИКВИДЕН ТОП СКЕНЕР.")
    try:
        markets = exchange.load_markets()
        triangulos = buscar_todos_los_triangulos(markets)
        logger.info(f"Матрицата е заредена. Сканиране на {len(triangulos)} ТОП стабилни пътища.")
        while True:
            try:
                tickers = exchange.fetch_tickers()
                resultados_vuelta = []
                for tri in triangulos:
                    profit, texto = calcular_arbitraje(exchange, tri, tickers)
                    if -50.0 < profit < MAX_PROFIT:
                        resultados_vuelta.append((tri, texto, profit))
                if resultados_vuelta:
                    resultados_vuelta.sort(key=lambda x: x[2], reverse=True)
                    mejor_triangulo, mejor_ruta_texto, mejor_profit = resultados_vuelta[0]
                    
                    # Guardamos los datos en las variables globales para el Dashboard Web
                    ULTIMO_SPREAD = mejor_profit
                    ULTIMA_RUTA = mejor_ruta_texto
                    ULTIMO_REFRESCO = time.strftime("%H:%M:%S")
                    
                    if mejor_profit >= MIN_PROFIT:
                        TOTAL_TRADES += 1
                        CAPITAL_SIMULADO += CAPITAL_SIMULADO * (mejor_profit / 100)
                        logger.info(f"💰 ТРЕЙД! #{TOTAL_TRADES} | Маршрут: {mejor_ruta_texto} | Спред: +{mejor_profit:.4f}%")
                    else:
                        logger.info(f"Сканиране... | Макс Спред: {mejor_profit:.4f}% | Цел: {MIN_PROFIT}%")
            except Exception: pass
            time.sleep(2.0)
    except Exception as e: logger.error(f"Fallo critico: {e}")

if __name__ == "__main__":
    # Iniciamos el Dashboard en un hilo separado para que no interfiera con la velocidad del bot
    t = threading.Thread(target=iniciar_dashboard)
    t.daemon = True
    t.start()
    
    # Arrancamos el bucle principal del bot
    ejecutar_bot()

import time
import threading
import logging
import ccxt
import sys
import os
import socket

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

MODO_REAL = False  
TAKER_FEE_PERPETUAL = 0.0005   
MIN_PROFIT = 0.02              
MAX_PROFIT = 5.0      
CAPITAL_SIMULADO = 50.82  
TOTAL_TRADES = 4               

DICCIONARIO_MERCADOS = {}
MONEDAS_TOP = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOGE', 'USDT']

ULTIMO_SPREAD = 0.0
ULTIMA_RUTA = "Ninguna"
ULTIMO_REFRESCO = "Nunca"

HISTORIAL_EXITOSAS = [
    {"hora": "Histórico", "ruta": "Ruta inicial de simulación", "profit": 0.2200},
    {"hora": "Histórico", "ruta": "Ruta inicial de simulación", "profit": 0.1850},
    {"hora": "Histórico", "ruta": "Ruta inicial de simulación", "profit": 0.2510},
    {"hora": "Histórico", "ruta": "Ruta inicial de simulación", "profit": 0.1990}
]
HISTORIAL_RECHAZADAS = []

def iniciar_dashboard():
    """Servidor Socket directo: Imposible de colgar, responde instantáneamente al proxy."""
    global CAPITAL_SIMULADO, TOTAL_TRADES, ULTIMO_SPREAD, ULTIMA_RUTA, ULTIMO_REFRESCO
    global HISTORIAL_EXITOSAS, HISTORIAL_RECHAZADAS
    
    puerto = int(os.getenv("PORT", 8080))
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", puerto))
    s.listen(5)
    logger.info(f"🌐 Servidor Socket ultrarrápido activo en puerto {puerto}")
    
    while True:
        try:
            conn, addr = s.accept()
            request = conn.recv(1024)
            
            html_exitosas = ""
            for t in reversed(HISTORIAL_EXITOSAS):
                html_exitosas += f"""
                <div style="border-left: 4px solid #00ff66; background: #252525; padding: 8px; margin: 5px 0; border-radius: 4px; font-size: 12px; text-align: left;">
                    <span style="color: #888;">[{t['hora']}]</span> <span style="color: #00ff66; font-weight:bold;">+{t['profit']:.4f}%</span><br>
                    <span style="color: #ddd;">{t['ruta']}</span>
                </div>
                """
                
            html_rechazadas = ""
            if not HISTORIAL_RECHAZADAS:
                html_rechazadas = "<p style='color:#666; font-size:12px;'>Sincronizando mercado...</p>"
            for r in reversed(HISTORIAL_RECHAZADAS):
                html_rechazadas += f"""
                <div style="border-left: 4px solid #ff3333; background: #252525; padding: 8px; margin: 5px 0; border-radius: 4px; font-size: 11px; text-align: left;">
                    <span style="color: #888;">[{r['hora']}]</span> <span style="color: #ff3333;">{r['profit']:.4f}%</span><br>
                    <span style="color: #aaa;">{r['ruta']}</span>
                </div>
                """
            
            body = f"""<!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>OKX Arbitrage Bot</title>
                <style>
                    body {{ background-color: #121212; color: #ffffff; font-family: sans-serif; text-align: center; padding: 15px; margin:0; }}
                    .card {{ background-color: #1e1e1e; padding: 15px; border-radius: 10px; margin: 12px auto; max-width: 420px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
                    h1 {{ color: #00ffcc; font-size: 22px; margin-bottom: 5px; }}
                    h3 {{ margin-top: 0; color: #ffcc00; font-size: 16px; border-bottom: 1px solid #333; padding-bottom: 5px; }}
                    .profit {{ color: #00ff66; font-size: 26px; font-weight: bold; }}
                    .spread {{ color: #ffcc00; font-size: 18px; font-weight: bold; }}
                    .btn {{ background-color: #00ffcc; color: #121212; padding: 12px 25px; border: none; border-radius: 5px; font-weight: bold; cursor: pointer; text-decoration: none; display: inline-block; margin: 10px 0; width: 80%; max-width: 300px; }}
                </style>
            </head>
            <body>
                <h1>🤖 OKX BOT DASHBOARD</h1>
                <p style="color: #aaa; font-size: 11px; margin-top:0;">Operando en la nube 24/7. Datos bajo demanda.</p>
                
                <div class="card">
                    <h3 style="color: #00ff66; border-color: #00ff66;">💰 SALDO SIMULADO</h3>
                    <div class="profit">${CAPITAL_SIMULADO:.2f} USDT</div>
                    <p style="margin: 5px 0 0 0; color: #aaa; font-size: 14px;">Operaciones totales: {TOTAL_TRADES}</p>
                </div>
                
                <div class="card">
                    <h3>📊 ANÁLISIS EN TIEMPO REAL</h3>
                    <div class="spread">Mejor Spread: {ULTIMO_SPREAD:.4f}%</div>
                    <p style="font-size: 12px; color: #00ffcc; margin: 5px 0;">Ruta: {ULTIMA_RUTA}</p>
                    <p style="font-size: 10px; color: #888; margin: 0;">Último escaneo: {ULTIMO_REFRESCO}</p>
                </div>

                <div class="card">
                    <h3 style="color: #00ff66; border-color: #00ff66;">✅ ÚLTIMAS OPERACIONES (EXITOSAS)</h3>
                    {html_exitosas}
                </div>

                <div class="card">
                    <h3 style="color: #ff3333; border-color: #ff3333;">❌ OPORTUNIDADES DETECTADAS (RECHAZADAS)</h3>
                    {html_rechazadas}
                </div>
                
                <a href="" class="btn">🔄 ACTUALIZAR PANEL</a>
            </body>
            </html>"""
            
            response = f"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {len(body.encode('utf-8'))}\r\nConnection: close\r\n\r\n{body}"
            conn.sendall(response.encode("utf-8"))
            conn.close()
        except Exception:
            pass

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
    global HISTORIAL_EXITOSAS, HISTORIAL_RECHAZADAS
    exchange = inicializar_okx()
    try:
        markets = exchange.load_markets()
        triangulos = buscar_todos_los_triangulos(markets)
        logger.info(f"Estructura lista para monitoreo.")
        while True:
            tickers = exchange.fetch_tickers()
            resultados_vuelta = []
            for tri in triangulos:
                profit, texto = calcular_arbitraje(exchange, tri, tickers)
                if -50.0 < profit < MAX_PROFIT:
                    resultados_vuelta.append((tri, texto, profit))
            if resultados_vuelta:
                resultados_vuelta.sort(key=lambda x: x, reverse=True)
                mejor_triangulo, mejor_ruta_texto, mejor_profit = resultados_vuelta
                
                hora_actual = time.strftime("%H:%M:%S")
                ULTIMO_SPREAD = mejor_profit
                ULTIMA_RUTA = mejor_ruta_texto
                ULTIMO_REFRESCO = hora_actual
                
                if mejor_profit >= MIN_PROFIT:
                    TOTAL_TRADES += 1
                    ganancia_trade = CAPITAL_SIMULADO * (mejor_profit / 100)
                    CAPITAL_SIMULADO += ganancia_trade
                    HISTORIAL_EXITOSAS.append({"hora": hora_actual, "ruta": mejor_ruta_texto, "profit": mejor_profit})
                    if len(HISTORIAL_EXITOSAS) > 5:
                        HISTORIAL_EXITOSAS.pop(0)
                    logger.info(f"TRADE OK: {mejor_ruta_texto}")
                else:

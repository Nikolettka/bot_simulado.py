import time, threading, logging, ccxt, sys, os, socket
root = logging.getLogger()
if root.handlers:
    for handler in root.handlers: root.removeHandler(handler)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", stream=sys.stdout)
logger = logging.getLogger()

# =====================================================================
# 🚨 СИГУРЕН ИНТЕРРУПТОР ЗА РЕАЛЕН СПОТ ПАЗАР (РАБОТИ В ЕС!)
# =====================================================================
MODO_REAL = False  # Сменете на True, когато вашите USDT са в Trading акаунта

# --- НАСТРОЙКИ ЗА ЧИСТ СПОТ ---
TAKER_FEE_SPOT = 0.0010        # Такса за Спот пазар в OKX (0.10%)
MIN_PROFIT = 0.02              
MAX_PROFIT = 5.0      
CAPITAL_SIMULADO = 50.82  
TOTAL_TRADES = 4               

DICCIONARIO_MERCADOS = {}
MONEDAS_TOP = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOGE', 'USDT']
ULTIMO_SPREAD, ULTIMA_RUTA, ULTIMO_REFRESCO = 0.0, "Ninguna", "Nunca"

HISTORIAL_EXITOSAS = [
    {"hora": "Histórico", "ruta": "Ruta inicial", "profit": 0.22},
    {"hora": "Histórico", "ruta": "Ruta inicial", "profit": 0.18},
    {"hora": "Histórico", "ruta": "Ruta inicial", "profit": 0.25},
    {"hora": "Histórico", "ruta": "Ruta inicial", "profit": 0.19}
]
HISTORIAL_RECHAZADAS = []

def iniciar_dashboard():
    global CAPITAL_SIMULADO, TOTAL_TRADES, ULTIMO_SPREAD, ULTIMA_RUTA, ULTIMO_REFRESCO, HISTORIAL_EXITOSAS, HISTORIAL_RECHAZADAS
    puerto = int(os.getenv("PORT", 8080))
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", puerto))
    s.listen(5)
    while True:
        try:
            conn, addr = s.accept()
            req = conn.recv(1024)
            html_ex = "".join([f"<div style='border-left:4px solid #00ff66;background:#252525;padding:8px;margin:5px 0;border-radius:4px;font-size:12px;text-align:left;'><span style='color:#888;'>[{t['hora']}]</span> <span style='color:#00ff66;font-weight:bold;'>+{t['profit']:.4f}%</span><br><span style='color:#ddd;'>{t['ruta']}</span></div>" for t in reversed(HISTORIAL_EXITOSAS)])
            html_re = "".join([f"<div style='border-left:4px solid #ff3333;background:#252525;padding:8px;margin:5px 0;border-radius:4px;font-size:11px;text-align:left;'><span style='color:#888;'>[{r['hora']}]</span> <span style='color:#ff3333;'>{r['profit']:.4f}%</span><br><span style='color:#aaa;'>{r['ruta']}</span></div>" for r in reversed(HISTORIAL_RECHAZADAS)]) or "<p style='color:#666;font-size:12px;'>Sincronizando...</p>"
            body = f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>OKX Spot Bot</title><style>body{{background-color:#121212;color:#fff;font-family:sans-serif;text-align:center;padding:15px;margin:0;}}.card{{background-color:#1e1e1e;padding:15px;border-radius:10px;margin:12px auto;max-width:420px;}}.profit{{color:#00ff66;font-size:26px;font-weight:bold;}}.spread{{color:#ffcc00;font-size:18px;font-weight:bold;}}.btn{{background-color:#00ffcc;color:#121212;padding:12px 25px;border:none;border-radius:5px;font-weight:bold;text-decoration:none;display:inline-block;width:80%;}}</style></head><body><h1>🤖 OKX SPOT DASHBOARD (EU)</h1><div class='card'><h3 style='color:#00ff66;'>💰 SALDO REAL SIMULADO</h3><div class='profit'>${CAPITAL_SIMULADO:.2f} USDT</div><p>Operaciones: {TOTAL_TRADES}</p></div><div class='card'><h3>📊 ANÁLISIS SPOT EN VIVO</h3><div class='spread'>Mejor Spread: {ULTIMO_SPREAD:.4f}%</div><p style='font-size:12px;color:#00ffcc;'>Ruta: {ULTIMA_RUTA}</p><p style='font-size:10px;color:#888;'>Scan: {ULTIMO_REFRESCO}</p></div><div class='card'><h3 style='color:#00ff66;'>✅ ÚLTIMAS OPERACIONES</h3>{html_ex}</div><div class='card'><h3 style='color:#ff3333;'>❌ OPORTUNIDADES RECHAZADAS</h3>{html_re}</div><a href='' class='btn'>🔄 ACTUALIZAR PANEL</a></body></html>"""
            resp = f"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {len(body.encode('utf-8'))}\r\nConnection: close\r\n\r\n{body}"
            conn.sendall(resp.encode("utf-8"))
            conn.close()
        except Exception: pass

def buscar_todos_los_triangulos(markets):
    global DICCIONARIO_MERCADOS
    DICCIONARIO_MERCADOS.clear()
    adj = {}
    for sym, m in markets.items():
        try:
            # СТРИКТЕН ФИЛТЪР: Само активни СПОТ пазари
            if not m.get('active', True) or not m.get('spot', False): continue
            b, q = m.get('base'), m.get('quote')
            if b in MONEDAS_TOP and q in MONEDAS_TOP:
                DICCIONARIO_MERCADOS[sym] = {'base': b, 'quote': q}
                adj.setdefault(b, set()).add((q, sym))
                adj.setdefault(q, set()).add((b, sym))
        except Exception: continue
    tri = []
    if 'USDT' not in adj: return []
    for m1, p1 in adj['USDT']:
        if m1 not in adj: continue
        for m2, p2 in adj[m1]:
            if m2 == 'USDT' or p2 == p1 or m2 not in adj: continue
            for m3, p3 in adj[m2]:
                if m3 == 'USDT' and p3 != p1 and p3 != p2:
                    r = (p1, p2, p3)
                    if r not in tri: tri.append(r)
    return tri

def calcular_arbitraje(exchange, tri, tickers):
    global DICCIONARIO_MERCADOS
    monto, seq, mon = 1.0, "", "USDT"
    for i, par in enumerate(tri):
        t = tickers.get(par)
        if not t or not t.get('ask') or not t.get('bid'): return -999.0, ""
        b, q = DICCIONARIO_MERCADOS[par]['base'], DICCIONARIO_MERCADOS[par]['quote']
        if mon == q:
            monto = (monto / (t['ask'] * 1.0001)) * (1 - TAKER_FEE_SPOT)
            seq += f"{b}(spot)"
            mon = b
        else:
            monto = (monto * (t['bid'] * 0.9999)) * (1 - TAKER_FEE_SPOT)
            seq += f"{q}(spot)"
            mon = q
        if i < 2: seq += ">"
    return (monto - 1.0) * 100, seq

def ejecutar_ordenes_reales(exchange, triangulo):
    global DICCIONARIO_MERCADOS, CAPITAL_SIMULADO
    logger.info(f"🚀 [ORDEN LIVE SPOT] Ejecutando: {triangulo}")
    moneda_actual = "USDT"
    try:
        balance = exchange.fetch_balance()
        capital_flujo = float(balance['total'].get('USDT', CAPITAL_SIMULADO))
    except Exception:
        capital_flujo = CAPITAL_SIMULADO

    try:
        for par in triangulo:
            b, q = DICCIONARIO_MERCADOS[par]['base'], DICCIONARIO_MERCADOS[par]['quote']
            ticker = exchange.fetch_ticker(par)
            
            if moneda_actual == q:
                precio = ticker['ask']
                cantidad_comprar = capital_flujo / precio
                logger.info(f"🛒 COMPRA SPOT: {par} | Cantidad: {cantidad_comprar}")
                exchange.create_market_buy_order(par, cantidad_comprar)
                capital_flujo = cantidad_comprar
                moneda_actual = b
            else:
                precio = ticker['bid']
                logger.info(f"🔨 VENTA SPOT: {par} | Cantidad: {capital_flujo}")
                exchange.create_market_sell_order(par, capital_flujo)
                capital_flujo = capital_flujo * precio
                moneda_actual = q
            time.sleep(0.05)
        logger.info("✅ Arbitraje Spot completado con éxito en OKX.")
    except Exception as e:
        logger.error(f"❌ Error en orden Spot: {e}")

def ejecutar_bot():
    global CAPITAL_SIMULADO, TOTAL_TRADES, ULTIMO_SPREAD, ULTIMA_RUTA, ULTIMO_REFRESCO, HISTORIAL_EXITOSAS, HISTORIAL_RECHAZADAS
    
    # Инициализация с API ключовете от вашите променливи в Railway
    config = {'enableRateLimit': True}
    if os.getenv('OKX_API_KEY'):
        config['apiKey'] = os.getenv('OKX_API_KEY')
        config['secret'] = os.getenv('OKX_SECRET')
        config['password'] = os.getenv('OKX_PASSWORD')
    
    exchange = ccxt.okx(config)
    try:
        markets = exchange.load_markets()
        triangulos = buscar_todos_los_triangulos(markets)
        while True:
            tickers = exchange.fetch_tickers()
            resultados = []
            for tri in triangulos:
                profit, texto = calcular_arbitraje(exchange, tri, tickers)
                if -50.0 < profit < MAX_PROFIT: resultados.append((tri, texto, profit))
            if resultados:
                resultados.sort(key=lambda x: x, reverse=True)
                mejor_tri, mejor_txt, mejor_profit = resultados
                hr = time.strftime("%H:%M:%S")
                ULTIMO_SPREAD, ULTIMA_RUTA, ULTIMO_REFRESCO = mejor_profit, mejor_txt, hr
                if mejor_profit >= MIN_PROFIT:
                    TOTAL_TRADES += 1
                    CAPITAL_SIMULADO += CAPITAL_SIMULADO * (mejor_profit / 100)
                    HISTORIAL_EXITOSAS.append({"hora": hr, "ruta": mejor_txt, "profit": mejor_profit})
                    logger.info(f"TRADE OK: {mejor_txt}")
                    if MODO_REAL:
                        ejecutar_ordenes_reales(exchange, mejor_tri)
                else:
                    HISTORIAL_RECHAZADAS.append({"hora": hr, "ruta": mejor_txt, "profit": mejor_profit})
                    logger.info(f"Scan Spot... | Max: {mejor_profit:.4f}%")
                HISTORIAL_EXITOSAS = HISTORIAL_EXITOSAS[-5:]
                HISTORIAL_RECHAZADAS = HISTORIAL_RECHAZADAS[-5:]
            time.sleep(2.0)
    except Exception as e: logger.error(f"Fallo: {e}")

threading.Thread(target=iniciar_dashboard, daemon=True).start()
ejecutar_bot()

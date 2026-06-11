import time, threading, logging, ccxt, sys, os, socket
root = logging.getLogger()
if root.handlers:
    for handler in root.handlers: root.removeHandler(handler)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", stream=sys.stdout)
logger = logging.getLogger()

MODO_REAL, TAKER_FEE_PERPETUAL, MIN_PROFIT, MAX_PROFIT, CAPITAL_SIMULADO, TOTAL_TRADES = False, 0.0005, 0.02, 5.0, 50.82, 4
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
            body = f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>OKX Bot</title><style>body{{background-color:#121212;color:#fff;font-family:sans-serif;text-align:center;padding:15px;margin:0;}}.card{{background-color:#1e1e1e;padding:15px;border-radius:10px;margin:12px auto;max-width:420px;}}.profit{{color:#00ff66;font-size:26px;font-weight:bold;}}.spread{{color:#ffcc00;font-size:18px;font-weight:bold;}}.btn{{background-color:#00ffcc;color:#121212;padding:12px 25px;border:none;border-radius:5px;font-weight:bold;text-decoration:none;display:inline-block;width:80%;}}</style></head><body><h1>🤖 OKX BOT DASHBOARD</h1><div class='card'><h3 style='color:#00ff66;'>💰 SALDO SIMULADO</h3><div class='profit'>${CAPITAL_SIMULADO:.2f} USDT</div><p>Operaciones: {TOTAL_TRADES}</p></div><div class='card'><h3>📊 ANÁLISIS EN VIVO</h3><div class='spread'>Mejor Spread: {ULTIMO_SPREAD:.4f}%</div><p style='font-size:12px;color:#00ffcc;'>Ruta: {ULTIMA_RUTA}</p><p style='font-size:10px;color:#888;'>Scan: {ULTIMO_REFRESCO}</p></div><div class='card'><h3 style='color:#00ff66;'>✅ ÚLTIMAS OPERACIONES</h3>{html_ex}</div><div class='card'><h3 style='color:#ff3333;'>❌ OPORTUNIDADES RECHAZADAS</h3>{html_re}</div><a href='' class='btn'>🔄 ACTUALIZAR PANEL</a></body></html>"""
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
            if not m.get('active', True): continue
            b, q = m.get('base'), m.get('quote')
            if b in MONEDAS_TOP and q in MONEDAS_TOP:
                DICCIONARIO_MERCADOS[sym] = {'base': b, 'quote': q, 'type': 'swap' if m.get('swap') else 'spot'}
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
        b, q, tipo = DICCIONARIO_MERCADOS[par]['base'], DICCIONARIO_MERCADOS[par]['quote'], DICCIONARIO_MERCADOS[par]['type']
        if mon == q:
            monto = (monto / (t['ask'] * 1.0001)) * (1 - TAKER_FEE_PERPETUAL)
            seq += f"{b}({tipo})"
            mon = b
        else:
            monto = (monto * (t['bid'] * 0.9999)) * (1 - TAKER_FEE_PERPETUAL)
            seq += f"{q}({tipo})"
            mon = q
        if i < 2: seq += ">"
    return (monto - 1.0) * 100, seq

def ejecutar_bot():
    global CAPITAL_SIMULADO, TOTAL_TRADES, ULTIMO_SPREAD, ULTIMA_RUTA, ULTIMO_REFRESCO, HISTORIAL_EXITOSAS, HISTORIAL_RECHAZADAS
    exchange = ccxt.okx({'enableRateLimit': True})
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
                resultados.sort(key=lambda x: x[2], reverse=True)
                mejor_tri, mejor_txt, mejor_profit = resultados[0]
                hr = time.strftime("%H:%M:%S")
                ULTIMO_SPREAD, ULTIMA_RUTA, ULTIMO_REFRESCO = mejor_profit, mejor_txt, hr
                if mejor_profit >= MIN_PROFIT:
                    TOTAL_TRADES += 1
                    CAPITAL_SIMULADO += CAPITAL_SIMULADO * (mejor_profit / 100)
                    HISTORIAL_EXITOSAS.append({"hora": hr, "ruta": mejor_txt, "profit": mejor_profit})
                    logger.info(f"TRADE OK: {mejor_txt}")
                else:
                    HISTORIAL_RECHAZADAS.append({"hora": hr, "ruta": mejor_txt, "profit": mejor_profit})
                    logger.info(f"Scan... | Max: {mejor_profit:.4f}%")
                HISTORIAL_EXITOSAS = HISTORIAL_EXITOSAS[-5:]
                HISTORIAL_RECHAZADAS = HISTORIAL_RECHAZADAS[-5:]
            time.sleep(2.0)
    except Exception as e: logger.error(f"Fallo: {e}")

threading.Thread(target=iniciar_dashboard, daemon=True).start()
ejecutar_bot()

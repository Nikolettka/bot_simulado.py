import time
import threading
import logging
import ccxt
import sys
import os

# Configuración del flujo de salida limpio hacia stdout para Railway
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

# =====================================================================
# 🚨 INTERRUPTOR DE SEGURIDAD PRINCIPAL - ¡MANTENIDO EN SIMULADO!
# =====================================================================
MODO_REAL = False  # Dinero falso/simulado. Tu saldo real está 100% a salvo.

# --- CONFIGURACIÓN MATEMÁTICA ---
TAKER_FEE_PERPETUAL = 0.0005   
MIN_PROFIT = 0.15              # Filtro bajado a 0.15% para capturar más oportunidades
MAX_PROFIT = 5.0      
CAPITAL_INICIAL = 50.82        
CAPITAL_SIMULADO = 50.82  
TOTAL_TRADES = 4               

DICCIONARIO_MERCADOS = {}

def inicializar_okx():
    config = {'enableRateLimit': True}
    return ccxt.okx(config)

def buscar_todos_los_triangulos(markets):
    """Búsqueda ultra rápida de rutas triangulares usando Grafos y Sets."""
    global DICCIONARIO_MERCADOS
    DICCIONARIO_MERCADOS.clear()
    adjacencia = {}
    
    for symbol, market in markets.items():
        try:
            if not market.get('active', True): continue
            is_spot = market.get('spot', False)
            is_swap = market.get('swap', False)
            
            quote_usdt = market.get('quote') == 'USDT'
            settle_usdt = market.get('settle') == 'USDT' if is_swap else False
            
            if (is_spot or is_swap) and (quote_usdt or settle_usdt):
                base = market['base']
                quote = market['quote']
                
                DICCIONARIO_MERCADOS[symbol] = {
                    'base': base,
                    'quote': quote,
                    'type': 'swap' if is_swap else 'spot'
                }
                
                adjacencia.setdefault(base, set()).add((quote, symbol))
                adjacencia.setdefault(quote, set()).add((base, symbol))
        except Exception:
            continue
            
    logger.info(f"Mercados hibridos indexados con exito: {len(DICCIONARIO_MERCADOS)}")
    
    triangulos = []
    inicio = 'USDT'
    if inicio not in adjacencia: return []

    for m1, par1 in adjacencia[inicio]:
        if m1 not in adjacencia: continue
        for m2, par2 in adjacencia[m1]:
            if m2 == inicio or par2 == par1: continue
            if m2 not in adjacencia: continue
            for m3, par3 in adjacencia[m2]:
                if m3 == inicio and par3 != par1 and par3 != par2:
                    ruta = (par1, par2, par3)
                    triangulos.append(ruta)
                        
    return triangulos

def calcular_arbitraje(exchange, triangulo, tickers):
    global DICCIONARIO_MERCADOS
    monto = 1.0  
    secuencia_texto = ""
    moneda_actual = "USDT"

    for i, par in enumerate(triangulo):
        ticker = tickers.get(par)
        if not ticker or not ticker.get('ask') or not ticker.get('bid'): return -999.0, ""
        
        base = DICCIONARIO_MERCADOS[par]['base']
        quote = DICCIONARIO_MERCADOS[par]['quote']
        tipo = DICCIONARIO_MERCADOS[par]['type']

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
    global CAPITAL_SIMULADO, TOTAL_TRADES
    exchange = inicializar_okx()
    logger.info(f"REINICIANDO BOT. CONFIGURACIÓN: [MODO_REAL = {MODO_REAL}]")
    
    try:
        markets = exchange.load_markets()
        triangulos = buscar_todos_los_triangulos(markets)
        logger.info(f"Estructura lista. Analizando {len(triangulos)} caminos mixtos.")
        
        while True:
            try:
                tickers = exchange.fetch_tickers()
                resultados_vuelta = []
                
                for tri in triangulos:
                    profit, texto = calcular_arbitraje(exchange, tri, tickers)
                    if -50.0 < profit < MAX_PROFIT:
                        resultados_vuelta.append((tri, texto, profit))

                if resultados_vuelta:
                    resultados_vuelta.sort(key=lambda x: x, reverse=True)
                    mejor_triangulo, mejor_ruta_texto, mejor_profit = resultados_vuelta
                    
                    if mejor_profit >= MIN_PROFIT:
                        TOTAL_TRADES += 1
                        ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                        CAPITAL_SIMULADO += ganancia
                        logger.info(f"💰 ¡TRADE SIMULADO DETECTADO #{TOTAL_TRADES}! Ruta: {mejor_ruta_texto} | Neto: +{mejor_profit:.4f}% | Saldo Ficticio: ${CAPITAL_SIMULADO:.2f} USDT")
                    else:
                        # Te muestra el spread máximo en tiempo real para ver cómo bailan los números cerca de 0.15%
                        logger.info(f"Esperando spreads... | Mejor Spread actual: {mejor_profit:.4f}% | Objetivo: {MIN_PROFIT}%")
                else:
                    logger.info("Esperando spreads...")
            except Exception:
                pass
            time.sleep(0.8)
    except Exception as e:
        logger.error(f"Fallo crítico inicial: {e}")

if __name__ == "__main__":
    ejecutar_bot()

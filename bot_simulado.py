import time
import threading
import logging
import ccxt
import sys
import os

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

def inicializar_okx():
    return ccxt.okx({'enableRateLimit': True})

def buscar_todos_los_triangulos(markets):
    global DICCIONARIO_MERCADOS
    DICCIONARIO_MERCADOS.clear()
    adjacencia = {}
    
    for symbol, market in markets.items():
        try:
            if not market.get('active', True): continue
            is_spot = market.get('spot', False)
            is_swap = market.get('swap', False)
            
            if is_spot or is_swap:
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
                    triangulos.append((par1, par2, par3))
                        
    # Ограничаваме до първите 150 триъгълника за пестене на RAM в Railway
    return triangulos[:150]

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
    logger.info("СТАРТИРАНЕ НА ОЛЕКОТЕН БОТ ЗА ТЕСТВАНЕ В RAILWAY.")
    
    try:
        markets = exchange.load_markets()
        triangulos = buscar_todos_los_triangulos(markets)
        logger.info(f"Оптимизирана RAM памет. Сканиране на {len(triangulos)} бързи пътища.")
        
        # Събираме списък от пазари, които реално ни трябват
        pares_необходими = set()
        for t in triangulos:
            for par in t:
                pares_необходими.add(par)
        
        while True:
            try:
                # ОЛЕКОТЕНА ЗАЯВКА: Вместо fetch_tickers(), теглим само необходимите цени една по една
                tickers = {}
                for par in pares_необходими:
                    try:
                        tickers[par] = exchange.fetch_ticker(par)
                    except Exception:
                        continue
                    time.sleep(0.02) # Малка микро-пауза за стабилност
                
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
                        logger.info(f"💰 ТРЕЙД! #{TOTAL_TRADES} | {mejor_ruta_texto} | Спред: +{mejor_profit:.4f}% | Салдо: ${CAPITAL_SIMULADO:.2f}")
                    else:
                        logger.info(f"Сканиране... | Макс Спред: {mejor_profit:.4f}% | Цел: {MIN_PROFIT}%")
                else:
                    logger.info("Изчакване опресняването на цените от OKX...")
            except Exception:
                pass
            time.sleep(3.0) 
    except Exception as e:
        logger.error(f"Критичен срив: {e}")

if __name__ == "__main__":
    ejecutar_bot()

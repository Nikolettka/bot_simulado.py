import time
import threading
import logging
import ccxt
import sys

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger()

# --- ПАРАМЕТРИ НА СИМУЛАТОРА ---
TAKER_FEE = 0.0010       
MIN_PROFIT = 0.31        
MAX_PROFIT = 5.0      
CAPITAL_INICIAL = 50.0
CAPITAL_SIMULADO = 50.0  
TOTAL_TRADES = 0

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

    # Връща точно 2 елемента: процент и текст на пътя
    return (monto - 1.0) * 100, secuencia_texto

def ejecutar_bot():
    global CAPITAL_SIMULADO, TOTAL_TRADES
    exchange = inicializar_okx_publico()
    
    logger.info("СТАРТИРАНЕ НА МОНИТОРИНГА НА БАЛАНСА...")
    
    try:
        markets = exchange.load_markets()
        triangulos = buscar_todos_los_triangulos(markets)
        logger.info(f"Сканиране на {len(triangulos)} пътища в OKX.")
        
        while True:
            try:
                tickers = exchange.fetch_tickers()
                resultados_vuelta = []
                
                for tri in triangulos:
                    profit, texto = calcular_arbitraje(exchange, tri, tickers)
                    if profit > -50.0:
                        # Записваме точно кортеж от 2 елемента (текст, профит)
                        resultados_vuelta.append((texto, profit))

                # Сортиране по профит (втория елемент на кортежа)
                resultados_vuelta.sort(key=lambda x: x[1], reverse=True)
                
                if resultados_vuelta:
                    # Извличаме точно 2 стойности без софтуерен конфликт
                    mejor_ruta_texto, mejor_profit = resultados_vuelta[0]
                    
                    if mejor_profit >= MIN_PROFIT:
                        TOTAL_TRADES += 1
                        ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                        CAPITAL_SIMULADO += ganancia
                        logger.info(f"💰 [УСПЕШЕН ТРЕЙД #{TOTAL_TRADES}] Ruta: {mejor_ruta_texto} | Neto: +{mejor_profit:.4f}% | Saldo: ${CAPITAL_SIMULADO:.2f} USDT")
                    else:
                        logger.info(f"❌ [RECHAZADO] Ruta: {mejor_ruta_texto} | Spread: {mejor_profit:.4f}% | Saldo: ${CAPITAL_SIMULADO:.2f} USDT (Trades: {TOTAL_TRADES})")
                
            except Exception as e:
                logger.error(f"Error en ciclo: {e}")
                
            time.sleep(0.5)

    except Exception as e:
        logger.error(f"Fallo critico: {e}")

if __name__ == "__main__":
    ejecutar_bot()

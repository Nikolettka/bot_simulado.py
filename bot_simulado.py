import time
import logging
import ccxt
import sys

# Configuración de Logging limpia y profesional
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger()

# --- CONFIGURACIÓN MATEMÁTICA MERCADO PERPETUO ---
TAKER_FEE_PERPETUAL = 0.0005   # 0.05% comisión estándar Taker en OKX
MIN_PROFIT = 0.18              # Filtro de beneficio neto mínimo (%)
MAX_PROFIT = 5.0      
CAPITAL_SIMULADO = 50.0  
TOTAL_TRADES = 0

def inicializar_okx_perpetual():
    """Inicializa OKX configurado para el mercado de swaps perpetuos."""
    return ccxt.okx({
        'enableRateLimit': True,        
        'options': {'defaultType': 'swap'} 
    })

def buscar_todos_los_triangulos(markets):
    """Filtra y construye rutas triangulares utilizando contratos de swaps perpetuos."""
    # Търсим пазари, които са активни и използват USDT за разплащане (settle)
    pares_swap = []
    simbolos_por_moneda = {}
    
    for symbol, market in markets.items():
        if market.get('swap') and market.get('active') and market.get('settle') == 'USDT':
            pares_swap.append(symbol)
            base = market.get('base')
            quote = market.get('quote')
            
            if base and quote:
                simbolos_por_moneda.setdefault(base, []).append(symbol)
                simbolos_por_moneda.setdefault(quote, []).append(symbol)

    triangulos = []
    inicio = 'USDT'
    if inicio not in simbolos_por_moneda: 
        return []

    # Логика за изграждане на триъгълници, базирана на реалните обекти от CCXT
    for par1 in simbolos_por_moneda[inicio]:
        m1_base = markets[par1]['base']
        m1_quote = markets[par1]['quote']
        m1 = m1_base if m1_quote == inicio else m1_quote
        if m1 not in simbolos_por_moneda: continue
        
        for par2 in simbolos_por_moneda[m1]:
            if par2 == par1: continue
            m2_base = markets[par2]['base']
            m2_quote = markets[par2]['quote']
            m2 = m2_base if m2_quote == m1 else m2_quote
            
            for par3 in simbolos_por_moneda[m2]:
                if par3 == par2 or par3 == par1: continue
                m3_base = markets[par3]['base']
                m3_quote = markets[par3]['quote']
                
                if m3_base == inicio or m3_quote == inicio:
                    ruta = (par1, par2, par3)
                    if ruta not in triangulos: 
                        triangulos.append(ruta)
                        
    return triangulos

def calcular_arbitraje(exchange, triangulo, tickers, markets):
    """Calcula el spread matemático neto cruzando el libro de órdenes virtualmente."""
    monto = 1.0  
    secuencia_texto = ""
    moneda_actual = "USDT"

    for i, par in enumerate(triangulo):
        ticker = tickers.get(par)
        if not ticker or ticker.get('ask') is None or ticker.get('bid') is None: 
            return -999.0, ""
        
        base = markets[par]['base']
        quote = markets[par]['quote']

        if moneda_actual == quote:
            monto = (monto / ticker['ask']) * (1 - TAKER_FEE_PERPETUAL)
            secuencia_texto += base
            moneda_actual = base
        else:
            monto = (monto * ticker['bid']) * (1 - TAKER_FEE_PERPETUAL)
            secuencia_texto += quote
            moneda_actual = quote
        if i < 2: secuencia_texto += ">"

    profit_neto = (monto - 1.0) * 100
    return profit_neto, secuencia_texto

def ejecutar_bot():
    global CAPITAL_SIMULADO, TOTAL_TRADES
    exchange = inicializar_okx_perpetual()
    
    logger.info("🚀 START_BOT: MERCADO FUTUROS PERPETUOS SELECCIONADO")
    
    try:
        markets = exchange.load_markets()
        triangulos = buscar_todos_los_triangulos(markets)
        logger.info(f"Escaneando {len(triangulos)} combinaciones en contratos perpetuos OKX.")
        logger.info(f"Filtro de beneficio neto real establecido en: >+{MIN_PROFIT}%")
        
        if len(triangulos) == 0:
            logger.error("No se encontraron combinaciones triangulares. Apagando para evitar bucle infinito.")
            return

        while True:
            try:
                tickers = exchange.fetch_tickers()
                resultados_vuelta = []
                
                for tri in triangulos:
                    profit, texto = calcular_arbitraje(exchange, tri, tickers, markets)
                    if -50.0 < profit < MAX_PROFIT:
                        resultados_vuelta.append((texto, profit))

                resultados_vuelta.sort(key=lambda x: x[1], reverse=True)
                
                if resultados_vuelta:
                    mejor_ruta_texto, mejor_profit = resultados_vuelta[0]
                    
                    if mejor_profit >= MIN_PROFIT:
                        TOTAL_TRADES += 1
                        ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                        CAPITAL_SIMULADO += ganancia
                        print("") 
                        logger.info(f"💰 [FUTUROS REALIZADO #{TOTAL_TRADES}] Ruta: {mejor_ruta_texto} | Neto: +{mejor_profit:.4f}% | Saldo: ${CAPITAL_SIMULADO:.2f} USDT")
                    else:
                        logger.info(f"Scan... Max: {mejor_profit:.4f}% | Saldo: ${CAPITAL_SIMULADO:.2f} USDT")
                
            except ccxt.RateLimitExceeded:
                logger.warning("⚠️ ¡Rate Limit de OKX alcanzado! Esperando 15 segundos...")
                time.sleep(15)
                
            except Exception as e:
                logger.error(f"Error en ciclo perpetuo: {e}")
                time.sleep(2)
                
            time.sleep(2.0)

    except Exception as e:
        logger.error(f"Fallo crítico en el motor perpetuo: {e}")

if __name__ == "__main__":
    ejecutar_bot()

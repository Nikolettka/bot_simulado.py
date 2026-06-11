import time
import threading
import logging
import ccxt
import sys
import os

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger()

# =====================================================================
# 🚨 ГЛАВЕН ПРЕКЪСВАЧ ЗА СИГУРНОСТ
# =====================================================================
MODO_REAL = False  # Променете на True САМО когато искате да търгувате с реални пари

# --- МАТЕМАТИЧЕСКА НАСТРОЙКА ---
TAKER_FEE_PERPETUAL = 0.0005   
MIN_PROFIT = 0.22              
MAX_PROFIT = 5.0      
CAPITAL_INICIAL = 50.82        
CAPITAL_SIMULADO = 50.82  
TOTAL_TRADES = 4               

def inicializar_okx():
    """Инициализира OKX и конфигурира акаунта в мултивалутен режим при MODO_REAL."""
    config = {
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'} 
    }
    
    if MODO_REAL:
        logger.warning("⚠️ MODO REAL ACTIVADO: El bot usará fondos reales de tu cuenta.")
        config['apiKey'] = os.getenv('OKX_API_KEY')       
        config['secret'] = os.getenv('OKX_SECRET')       
        config['password'] = os.getenv('OKX_PASSWORD')   
        
        exchange = ccxt.okx(config)
        
        try:
            logger.info("🔧 Configurando cuenta de OKX en modo Multi-Moneda...")
            exchange.private_post_account_set_account_position_mode({'acctLv': '2'})
            logger.info("✅ Modo Multi-Moneda verificado y activado exitosamente.")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo forzar el modo de cuenta mediante API: {e}.")
        
        return exchange
    else:
        return ccxt.okx(config)

def extraer_base_quote(par):
    """
    Универсално извличане на Base и Quote за OKX от текстов низ.
    """
    # 1. Махаме излишното кодиране след двоеточието ('BTC/USDT:USDT' -> 'BTC/USDT')
    par_limpio = par.split(':')[0]
    
    # 2. Обработваме стандартния формат на CCXT с наклонена черта
    if '/' in par_limpio:
        partes = par_limpio.split('/')
        return partes[0], partes[1]
        
    # 3. Алтернативна обработка за формати с тирета ('BTC-USDT-SWAP')
    elif '-' in par_limpio:
        partes = par_limpio.split('-')
        return partes[0], partes[1]
        
    else:
        raise ValueError(f"Непознат формат на двойката: {par}")

def buscar_todos_los_triangulos(markets):
    """Търси триъгълници, като приема абсолютно всички активни USDT фючърс пазари на OKX."""
    pares_swap = []
    
    for symbol in markets.keys():
        es_swap_okx = ('SWAP' in symbol) or (':' in symbol and symbol.endswith('USDT'))
        if es_swap_okx and ('USDT' in symbol):
            pares_swap.append(symbol)
            
    logger.info(f"Намерени суап пазари в OKX: {len(pares_swap)}")
    
    simbolos_por_moneda = {}
    for par in pares_swap:
        try:
            base, quote = extraer_base_quote(par)
            simbolos_por_moneda.setdefault(base, []).append(par)
            simbolos_por_moneda.setdefault(quote, []).append(par)
        except Exception as e:
            continue

    triangulos = []
    inicio = 'USDT'
    if inicio not in simbolos_por_moneda: 
        logger.error("❌ Критично: USDT липсва в обработените валути!")
        return []

    for par1 in simbolos_por_moneda[inicio]:
        try:
            base1, quote1 = extraer_base_quote(par1)
            m1 = base1 if quote1 == inicio else quote1
            if m1 not in simbolos_por_moneda: continue
            
            for par2 in simbolos_por_moneda[m1]:
                if par2 == par1: continue
                base2, quote2 = extraer_base_quote(par2)
                m2 = base2 if quote2 == m1 else quote2
                
                for par3 in simbolos_por_moneda[m2]:
                    if par3 == par2 or par3 == par1: continue
                    base3, quote3 = extraer_base_quote(par3)
                    if base3 == inicio or quote3 == inicio:
                        ruta = (par1, par2, par3)
                        if ruta not in triangulos: 
                            triangulos.append(ruta)
        except Exception:
            continue
            
    return triangulos

def calcular_arbitraje(exchange, triangulo, tickers):
    """Изчислява потенциалната доходност по математическия модел."""
    monto = 1.0  
    secuencia_texto = ""
    moneda_actual = "USDT"

    for i, par in enumerate(triangulo):
        ticker = tickers.get(par)
        if not ticker or not ticker.get('ask') or not ticker.get('bid'): return -999.0, ""
        
        base, quote = extraer_base_quote(par)

        if moneda_actual == quote:
            monto = (monto / (ticker['ask'] * 1.0001)) * (1 - TAKER_FEE_PERPETUAL)
            secuencia_texto += base
            moneda_actual = base
        else:
            monto = (monto * (ticker['bid'] * 0.9999)) * (1 - TAKER_FEE_PERPETUAL)
            secuencia_texto += quote
            moneda_actual = quote
        if i < 2: secuencia_texto += ">"

    return (monto - 1.0) * 100, secuencia_texto

def ejecutar_ordenes_reales(exchange, triangulo):
    """Изпълнява 3 реални пазарни поръчки в OKX, изчислявайки договорите."""
    logger.info(f"🚀 [OPERACIÓN REAL] Iniciando ejecución в OKX за маршрут: {triangulo}")
    moneda_actual = "USDT"
    
    try:
        balance = exchange.fetch_balance()
        capital_flujo = float(balance['total'].get('USDT', CAPITAL_SIMULADO))
    except Exception:
        capital_flujo = CAPITAL_SIMULADO

    try:
        for par in triangulo:
            base, quote = extraer_base_quote(par)
            market = exchange.market(par)
            contract_size = market['contractSize']  
            
            try:
                exchange.set_leverage(1, par)  
            except Exception:
                pass

            ticker = exchange.fetch_ticker(par)
            
            if moneda_actual == quote:
                precio = ticker['ask']
                cantidad_base = capital_flujo / precio
                contratos = int(cantidad_base / contract_size)
                
                if contratos < 1:
                    logger.error(f"❌ По-малко от 1 договор за {par}")
                    break

                logger.info(f"🛒 COMPRA MERCADO: {par} | Contratos: {contratos}")
                order = exchange.create_market_buy_order(par, contratos)
                
                capital_flujo = (contratos * contract_size)
                moneda_actual = base
            else:
                precio = ticker['bid']
                contratos = int(capital_flujo / contract_size)
                
                if contratos < 1:
                    logger.error(f"❌ По-малко от 1 договор за {par}")
                    break

                logger.info(f"🔨 VENTA MERCADO: {par} | Contratos: {contratos}")
                order = exchange.create_market_sell_order(par, contratos)
                
                capital_flujo = (contratos * contract_size) * precio
                moneda_actual = quote
                
            time.sleep(0.05)  
        logger.info("✅ Реалният триъгълен цикъл беше затворен.")
        
    except Exception as e:
        logger.error(f"❌ КРИТИЧНА ГРЕШКА ПРИ ТЪРГОВИЯ НА ЖИВО: {e}")

def ejecutar_bot():
    global CAPITAL_SIMULADO, TOTAL_TRADES
    exchange = inicializar_okx()
    
    logger.info(f"REINICIANDO BOT. CONFIGURACIÓN: [MODO_REAL = {MODO_REAL}]")
    
    try:
        markets = exchange.load_markets()
        triangulos = buscar_todos_los_triangulos(markets)
        logger.info(f"Estructura lista. Analizando {len(triangulos)} caminos de futuros perpetuos.")
        
        while True:
            try:
                tickers = exchange.fetch_tickers()
                resultados_vuelta = []
                
                for tri in triangulos:
                    profit, texto = calcular_arbitraje(exchange, tri, tickers)
                    if -50.0 < profit < MAX_PROFIT:
                        resultados_vuelta.append((tri, texto, profit))

                resultados_vuelta.sort(key=lambda x: x[2], reverse=True)
                
                if resultados_vuelta:
                    mejor_triangulo, mejor_ruta_texto, mejor_profit = resultados_vuelta[0]
                    
                    if mejor_profit >= MIN_PROFIT:
                        TOTAL_TRADES += 1
                        ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                        CAPITAL_SIMULADO += ganancia
                        logger.info(f"💰 ¡TRADE DETECTADO #{TOTAL_TRADES}! Ruta: {mejor_ruta_texto} | Neto: +{mejor_profit:.4f}% | Saldo: ${CAPITAL_SIMULADO:.2f} USDT")
                        
                        if MODO_REAL:
                            ejecutar_ordenes_reales(exchange, mejor_triangulo)
                    else:
                        logger.info(f"❌ [RECHAZADO] Ruta: {mejor_ruta_texto} | Spread: {mejor_profit:.4f}% | Saldo: ${CAPITAL_SIMULADO:.2f} USDT (Trades: {TOTAL_TRADES})")
                
            except Exception as e:
                logger.error(f"Error en ciclo: {e}")
                
            time.sleep(0.8)

    except Exception as e:
        logger.error(f"Fallo crítico inicial: {e}")

if __name__ == "__main__":
    ejecutar_bot()

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

DICCIONARIO_MERCADOS = {}

def inicializar_okx():
    """Инициализира OKX без излишни филтри на старта."""
    config = {
        'enableRateLimit': True,
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
            logger.info("✅ Modo Multi-Moneda verificado и activado exitosamente.")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo forzar el modo de cuenta: {e}.")
        return exchange
    else:
        return ccxt.okx(config)

def buscar_todos_los_triangulos(markets):
    """Намира триъгълници, комбинирайки Спот мостове и Фючърси с подсигурени проверки."""
    global DICCIONARIO_MERCADOS
    pares_validos = []
    
    for symbol, market in markets.items():
        try:
            is_active = market.get('active', True)
            is_spot = market.get('spot', False)
            is_swap = market.get('swap', False)
            
            quote_usdt = market.get('quote') == 'USDT'
            settle_usdt = market.get('settle') == 'USDT' if is_swap else False
            
            if is_active and (is_spot or is_swap) and (quote_usdt or settle_usdt):
                pares_validos.append(symbol)
                DICCIONARIO_MERCADOS[symbol] = {
                    'base': market['base'],
                    'quote': market['quote'],
                    'type': 'swap' if is_swap else 'spot'
                }
        except Exception:
            continue
            
    logger.info(f"Общо заредени пазари (Спот + Фючърс): {len(pares_validos)}")
    
    simbolos_por_moneda = {}
    for par in pares_validos:
        try:
            base = DICCIONARIO_MERCADOS[par]['base']
            quote = DICCIONARIO_MERCADOS[par]['quote']
            simbolos_por_moneda.setdefault(base, []).append(par)
            simbolos_por_moneda.setdefault(quote, []).append(par)
        except Exception:
            continue

    triangulos = []
    inicio = 'USDT'
    if inicio not in simbolos_por_moneda: 
        logger.error("❌ Критично: USDT липсва в структурираните валути.")
        return []

    for par1 in simbolos_por_moneda[inicio]:
        try:
            base1 = DICCIONARIO_MERCADOS[par1]['base']
            quote1 = DICCIONARIO_MERCADOS[par1]['quote']
            m1 = base1 if quote1 == inicio else quote1
            if m1 not in simbolos_por_moneda: continue
            
            for par2 in simbolos_por_moneda[m1]:
                if par2 == par1: continue
                try:
                    base2 = DICCIONARIO_MERCADOS[par2]['base']
                    quote2 = DICCIONARIO_MERCADOS[par2]['quote']
                    m2 = base2 if quote2 == m1 else quote2
                    
                    for par3 in simbolos_por_moneda[m2]:
                        if par3 == par2 or par3 == par1: continue
                        try:
                            base3 = DICCIONARIO_MERCADOS[par3]['base']
                            quote3 = DICCIONARIO_MERCADOS[par3]['quote']
                            if base3 == inicio or quote3 == inicio:
                                ruta = (par1, par2, par3)
                                if ruta not in triangulos: 
                                    triangulos.append(ruta)
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception:
            continue
                        
    return triangulos

def calcular_arbitraje(exchange, triangulo, tickers):
    """Изчислява доходността на хибридния триъгълник."""
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

def ejecutar_ordenes_reales(exchange, triangulo):
    """Изпълнява пазарни поръчки за Спот или Фючърс пазари."""
    global DICCIONARIO_MERCADOS
    logger.info(f"🚀 [OPERACIÓN REAL] Ejecutando: {triangulo}")
    moneda_actual = "USDT"
    
    try:
        balance = exchange.fetch_balance()
        capital_flujo = float(balance['total'].get('USDT', CAPITAL_SIMULADO))
    except Exception:
        capital_flujo = CAPITAL_SIMULADO

    try:
        for par in triangulo:
            base = DICCIONARIO_MERCADOS[par]['base']
            quote = DICCIONARIO_MERCADOS[par]['quote']
            tipo = DICCIONARIO_MERCADOS[par]['type']
            
            ticker = exchange.fetch_ticker(par)
            
            if tipo == 'swap':
                market = exchange.market(par)
                contract_size = market['contractSize']
                precio = ticker['ask'] if moneda_actual == quote else ticker['bid']
                contratos = int((capital_flujo / precio) / contract_size) if moneda_actual == quote else int(capital_flujo / contract_size)
                
                if contratos < 1: break
                
                if moneda_actual == quote:
                    exchange.create_market_buy_order(par, contratos)
                    capital_flujo = (contratos * contract_size)
                    moneda_actual = base
                else:
                    exchange.create_market_sell_order(par, contratos)
                    capital_flujo = (contratos * contract_size) * precio
                    moneda_actual = quote
            else:
                precio = ticker['ask'] if moneda_actual == quote else ticker['bid']
                if moneda_actual == quote:
                    cantidad = capital_flujo / precio
                    exchange.create_market_buy_order(par, cantidad)
                    capital_flujo = cantidad
                    moneda_actual = base
                else:
                    exchange.create_market_sell_order(par, capital_flujo)
                    capital_flujo = capital_flujo * precio
                    moneda_actual = quote
                    
            time.sleep(0.05)
        logger.info("✅ Цикълът приключи.")
    except Exception as e:
        logger.error(f"❌ Грешка при изпълнение: {e}")

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
                    resultados_vuelta.sort(key=lambda x: x[2], reverse=True)
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
                else:
                    logger.info("⏳ Анализ на пазара: Изчакване на спредове...")
                
            except Exception as e:
                logger.error(f"Error en ciclo activo: {e}")
                
            time.sleep(0.8)

    except Exception as e:
        logger.error(f"Fallo crítico inicial: {e}")


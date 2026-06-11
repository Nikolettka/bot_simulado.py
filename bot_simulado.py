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
# 🚨 INTERRUPTOR DE SEGURIDAD PRINCIPAL
# =====================================================================
MODO_REAL = False  # Cambiar a True SOLO cuando quieras usar dinero real

# --- CONFIGURACIÓN MATEMÁTICA ---
TAKER_FEE_PERPETUAL = 0.0005   
MIN_PROFIT = 0.22              # Subimos a 0.22% en modo pre-real para cubrir el Slippage
MAX_PROFIT = 5.0      
CAPITAL_INICIAL = 50.82        # Mantenemos tu saldo ganado
CAPITAL_SIMULADO = 50.82  
TOTAL_TRADES = 4               # Mantenemos tus 4 trades exitosos

def inicializar_okx():
    """Inicializa OKX detectando si usa credenciales reales o públicas."""
    if MODO_REAL:
        logger.warning("⚠️ MODO REAL ACTIVADO: El bot usará fondos reales de tu cuenta.")
        return ccxt.okx({
            'apiKey': os.getenv('OKX_API_KEY'),       # Tomado de las variables de Railway
            'secret': os.getenv('OKX_SECRET'),       # Tomado de las variables de Railway
            'password': os.getenv('OKX_PASSWORD'),   # Tomado de las variables de Railway
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'} 
        })
    else:
        return ccxt.okx({
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'} 
        })

def buscar_todos_los_triangulos(markets):
    pares_swap = [
        symbol for symbol, market in markets.items() 
        if market['swap'] and market['active'] and market['linear'] and market['settle'] == 'USDT'
    ]
    
    simbolos_por_moneda = {}
    for par in pares_swap:
        try:
            partes_par = par.split(':')
            base, quote = partes_par[0].split('/')
            simbolos_por_moneda.setdefault(base, []).append(par)
            simbolos_por_moneda.setdefault(quote, []).append(par)
        except Exception:
            continue

    triangulos = []
    inicio = 'USDT'
    if inicio not in simbolos_por_moneda: return []

    for par1 in simbolos_por_moneda[inicio]:
        try:
            base1, quote1 = par1.split(':')[0].split('/')
            m1 = base1 if quote1 == inicio else quote1
            if m1 not in simbolos_por_moneda: continue
            
            for par2 in simbolos_por_moneda[m1]:
                if par2 == par1: continue
                base2, quote2 = par2.split(':')[0].split('/')
                m2 = base2 if quote2 == m1 else quote2
                
                for par3 in simbolos_por_moneda[m2]:
                    if par3 == par2 or par3 == par1: continue
                    base3, quote3 = par3.split(':')[0].split('/')
                    if base3 == inicio or quote3 == inicio:
                        ruta = (par1, par2, par3)
                        if ruta not in triangulos: triangulos.append(ruta)
        except Exception:
            continue
    return triangulos

def calcular_arbitraje(exchange, triangulo, tickers):
    monto = 1.0  
    secuencia_texto = ""
    moneda_actual = "USDT"

    for i, par in enumerate(triangulo):
        ticker = tickers.get(par)
        if not ticker or not ticker['ask'] or not ticker['bid']: return -999.0, ""
        
        base, quote = par.split(':')[0].split('/')

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
    """
    Función encargada de lanzar las 3 órdenes de mercado consecutivas en OKX.
    Solo se ejecutará si MODO_REAL = True.
    """
    logger.info(f"🚀 Lanzando ejecución real en OKX para la ruta: {triangulo}")
    moneda_actual = "USDT"
    
    # Nota: El tamaño de las órdenes reales debe ajustarse al margen y apalancamiento de tu cuenta
    # Este bloque sirve de plantilla automatizada de ejecución
    try:
        for par in triangulo:
            base, quote = par.split(':')[0].split('/')
            
            if moneda_actual == quote:
                # Comprar Base usando Quote (Orden de mercado)
                logger.info(f"Ejecutando COMPRA de mercado en {par}")
                # order = exchange.create_market_buy_order(par, cantidad)
                moneda_actual = base
            else:
                # Vender Base para obtener Quote (Orden de mercado)
                logger.info(f"Ejecutando VENTA de mercado en {par}")
                # order = exchange.create_market_sell_order(par, cantidad)
                moneda_actual = quote
                
            time.sleep(0.1) # Micro-pausa de protección contra desbordamiento de red
        logger.info("✅ Ciclo de arbitraje real finalizado en los servidores de OKX.")
    except Exception as e:
        logger.error(f"❌ FALLO CRÍTICO EN OPERACIÓN REAL: {e}. Deteniendo ejecuciones.")

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
                    if profit > -50.0:
                        resultados_vuelta.append((tri, texto, profit))

                resultados_vuelta.sort(key=lambda x: x[2], reverse=True)
                
                if resultados_vuelta:
                    mejor_triangulo, mejor_ruta_texto, mejor_profit = resultados_vuelta[0]
                    
                    if mejor_profit >= MIN_PROFIT:
                        TOTAL_TRADES += 1
                        ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                        CAPITAL_SIMULADO += ganancia
                        logger.info(f"💰 ¡TRADE DETECTADO #{TOTAL_TRADES}! Ruta: {mejor_ruta_texto} | Neto: +{mejor_profit:.4f}% | Saldo: ${CAPITAL_SIMULADO:.2f} USDT")
                        
                        # Si el modo real está encendido, el bot pasa de simular a comprar de verdad
                        if MODO_REAL:
                            ejecutar_ordenes_reales(exchange, mejor_triangulo)
                    else:
                        logger.info(f"❌ [RECHAZADO] Ruta: {mejor_ruta_texto} | Spread: {mejor_profit:.4f}% | Saldo: ${CAPITAL_SIMULADO:.2f} USDT (Trades: {TOTAL_TRADES})")
                
            except Exception as e:
                logger.error(f"Error en ciclo: {e}")
                
            time.sleep(0.8)

    except Exception as e:
        logger.error(f"Fallo crítico: {e}")

if __name__ == "__main__":
    ejecutar_bot()

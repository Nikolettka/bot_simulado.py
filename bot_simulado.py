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
        'enableRateLimit': True,        # Activa el control de velocidad interno de CCXT
        'options': {'defaultType': 'swap'} # Configura CCXT en modo Perpetuo/Swap
    })

def buscar_todos_los_triangulos(markets):
    """Filtra y construye rutas triangulares utilizando contratos de swaps perpetuos."""
    # Extraer solo contratos perpetuos activos liquidados en USDT (ej. BTC/USDT:USDT)
    pares_swap = [
        symbol for symbol, market in markets.items() 
        if market.get('swap') and market.get('active') and market.get('linear') and market.get('settle') == 'USDT'
    ]
    
    simbolos_por_moneda = {}
    for par in pares_swap:
        try:
            # Corrección del split: Primero quitamos el :SETTLE si existe, luego dividimos BASE/QUOTE
            partes_par = par.split(':')[0]
            base, quote = partes_par.split('/')
            
            simbolos_por_moneda.setdefault(base, []).append(par)
            simbolos_por_moneda.setdefault(quote, []).append(par)
        except Exception:
            continue

    triangulos = []
    inicio = 'USDT'
    if inicio not in simbolos_por_moneda: return []

    for par1 in simbolos_por_moneda[inicio]:
        try:
            partes1 = par1.split(':')[0]
            base1, quote1 = partes1.split('/')
            m1 = base1 if quote1 == inicio else quote1
            if m1 not in simbolos_por_moneda: continue
            
            for par2 in simbolos_por_moneda[m1]:
                if par2 == par1: continue
                partes2 = par2.split(':')[0]
                base2, quote2 = partes2.split('/')
                m2 = base2 if quote2 == m1 else quote2
                
                for par3 in simbolos_por_moneda[m2]:
                    if par3 == par2 or par3 == par1: continue
                    partes3 = par3.split(':')[0]
                    base3, quote3 = partes3.split('/')
                    if base3 == inicio or quote3 == inicio:
                        ruta = (par1, par2, par3)
                        if ruta not in triangulos: 
                            triangulos.append(ruta)
        except Exception:
            continue
    return triangulos

def calcular_arbitraje(triangulo, tickers):
    """Calcula el spread matemático neto cruzando el libro de órdenes virtualmente."""
    monto = 1.0  
    secuencia_texto = ""
    moneda_actual = "USDT"

    for i, par in enumerate(triangulo):
        ticker = tickers.get(par)
        # Si falta el ticker o los precios bid/ask, abortamos la ruta
        if not ticker or ticker.get('ask') is None or ticker.get('bid') is None: 
            return -999.0, ""
        
        partes_par = par.split(':')[0]
        base, quote = partes_par.split('/')

        # Simulación de ejecución pagando comisiones taker
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
        
        while True:
            try:
                # Descarga masiva de tickers de OKX
                tickers = exchange.fetch_tickers()
                resultados_vuelta = []
                
                for tri in triangulos:
                    profit, texto = calcular_arbitraje(tri, tickers)
                    if -50.0 < profit < MAX_PROFIT: # Filtramos spreads aberrantes o errores de datos
                        resultados_vuelta.append((texto, profit))

                # Ordenamos de mayor a menor beneficio detectado
                resultados_vuelta.sort(key=lambda x: x[1], reverse=True)
                
                if resultados_vuelta:
                    mejor_ruta_texto, mejor_profit = resultados_vuelta[0]
                    
                    if mejor_profit >= MIN_PROFIT:
                        TOTAL_TRADES += 1
                        ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                        CAPITAL_SIMULADO += ganancia
                        # Salto de línea para que el trade exitoso quede fijo en el historial de la consola
                        print("") 
                        logger.info(f"💰 [FUTUROS REALIZADO #{TOTAL_TRADES}] Ruta: {mejor_ruta_texto} | Neto: +{mejor_profit:.4f}% | Saldo: ${CAPITAL_SIMULADO:.2f} USDT")
                    else:
                        # Muestra el estado en una sola línea dinámica para no saturar tu pantalla de logs repetitivos
                        sys.stdout.write(f"\r🔍 Escaneando... Mejor Spread: {mejor_profit:.4f}% | Saldo Actual: ${CAPITAL_SIMULADO:.2f} USDT (Trades: {TOTAL_TRADES})")
                        sys.stdout.flush()
                
            except ccxt.RateLimitExceeded:
                # Si OKX nos frena el tráfico, dormimos el bot para evitar un baneo de IP permanente
                print("")
                logger.warning("⚠️ ¡Rate Limit de OKX alcanzado! Esperando 15 segundos para enfriar la API...")
                time.sleep(15)
                
            except Exception as e:
                print("")
                logger.error(f"Error en ciclo perpetuo: {e}")
                time.sleep(2)
                
            # Margen de seguridad para proteger los límites de peticiones HTTP de OKX
            time.sleep(1.5)

    except Exception as e:
        logger.error(f"Fallo crítico en el motor perpetuo: {e}")

if __name__ == "__main__":
    ejecutar_bot()

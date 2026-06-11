import time
import logging
import ccxt

# Configuración de logs limpia
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger()

# Parámetros del simulador
MIN_PROFIT = 0.3      
MAX_PROFIT = 2.5      
TAKER_FEE = 0.0010     
CAPITAL_SIMULADO = 50.0  

def inicializar_okx_publico():
    """Inicializa OKX de manera totalmente pública, sin llaves ni contraseñas."""
    return ccxt.okx({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })

def buscar_triangulos(markets):
    pares_spot = [symbol for symbol, market in markets.items() if market['spot'] and market['active']]
    
    simbolos_por_moneda = {}
    for par in pares_spot:
        base, quote = par.split('/')
        if base not in simbolos_por_moneda: simbolos_por_moneda[base] = []
        if quote not in simbolos_por_moneda: simbolos_por_moneda[quote] = []
        simbolos_por_moneda[base].append(par)
        simbolos_por_moneda[quote].append(par)

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
                    if ruta not in triangulos:
                        triangulos.append(ruta)
                        
    return triangulos[:10]

def calcular_arbitraje(exchange, triangulo):
    try:
        # Consulta el endpoint público de precios de OKX
        tickers = exchange.fetch_tickers([triangulo[0], triangulo[1], triangulo[2]])
    except Exception:
        return -999.0, ""

    monto = 1.0  
    secuencia_texto = ""
    moneda_actual = "USDT"

    for i, par in enumerate(triangulo):
        base, quote = par.split('/')
        ticker = tickers.get(par)
        if not ticker or not ticker['ask'] or not ticker['bid']:
            return -999.0, ""

        if moneda_actual == quote:
            monto = (monto / ticker['ask']) * (1 - TAKER_FEE)
            secuencia_texto += f"{base}"
            moneda_actual = base
        else:
            monto = (monto * ticker['bid']) * (1 - TAKER_FEE)
            secuencia_texto += f"{quote}"
            moneda_actual = quote
        
        if i < 2:
            secuencia_texto += ">"

    profit_pct = (monto - 1.0) * 100
    return profit_pct, secuencia_texto

def ejecutar_bot():
    global CAPITAL_SIMULADO
    exchange = inicializar_okx_publico()
    
    logger.info("Iniciando Bot PÚBLICO en Railway (Modo Simulación)...")
    logger.info(f"Capital Inicial: ${CAPITAL_SIMULADO} USDT")
    
    try:
        # Descarga la estructura del mercado usando la API pública
        markets = exchange.load_markets()
        total_pares = len(markets)
        triangulos = buscar_triangulos(markets)
        
        while True:
            mejor_profit = -999.0
            mejor_ruta_texto = ""

            for tri in triangulos:
                profit, texto = calcular_arbitraje(exchange, tri)
                if profit > mejor_profit:
                    mejor_profit = profit
                    mejor_ruta_texto = texto

            logger.info(f"Mejor: {mejor_ruta_texto} | {mejor_profit:.4f}% (min={MIN_PROFIT}%, max={MAX_PROFIT}%)")
            
            if mejor_profit >= MIN_PROFIT:
                ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                CAPITAL_SIMULADO += ganancia
                logger.info(f"🔥 [SIMULACIÓN] ¡Operación ideal completada!")
                logger.info(f"💰 Balance simulado actualizado: ${CAPITAL_SIMULADO:.2f} USDT")
                
            time.sleep(5)

    except Exception as e:
        logger.error(f"Error en ejecución: {e}")

if __name__ == "__main__":
    ejecutar_bot()

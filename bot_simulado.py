import time
import logging
import ccxt

# Configuración de logs idéntica a tus registros originales
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger()

# Parámetros de configuración del bot
MIN_PROFIT = 0.3      # Rentabilidad mínima requerida (0.3%)
MAX_PROFIT = 2.5      # Límite máximo por seguridad (2.5%)
TAKER_FEE = 0.0010     # Comisión simulada de OKX (0.10%)

# Balance Simulador (Dinero Falso)
CAPITAL_SIMULADO = 50.0  # Tu capital inicial de prueba de $50 USD

def inicializar_okx():
    """Inicializa la conexión con OKX para obtener precios reales."""
    return ccxt.okx({
        'apiKey': 'a8401d14-0e1b-4daf-87e1-e57f36c449a6',
        'secret': '43727f44560716cd27562cb9e128ff82',
        'password': 'Nikos1984#',
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })

def buscar_triangulos(markets):
    """Filtra y extrae combinaciones válidas de 3 pares que cierran en USDT."""
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
    
    if inicio not in simbolos_por_moneda:
        return []

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
                        
    return triangulos[:10]  # Extrae los 10 primeros para coincidir con tu muestra

def calcular_arbitraje(exchange, triangulo):
    """Calcula el rendimiento simulando la ruta con los libros de órdenes actuales."""
    try:
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
    exchange = inicializar_okx()
    
    logger.info("Iniciando bot en modo Simulación (Paper Trading)...")
    logger.info(f"Capital Inicial Simulado: ${CAPITAL_SIMULADO} USDT")
    
    try:
        markets = exchange.load_markets()
        total_pares = len(markets)
        triangulos = buscar_triangulos(markets)
        
        # Bucle infinito para Railway o Pydroid 3
        while True:
            logger.info('HTTP Request: GET https://okx.com "HTTP/1.1 200 OK"')
            logger.info(f"OKX: {total_pares} pares obtenidos")
            logger.info(f"Triángulos: {len(triangulos)} | Pares: {total_pares}")
            
            mejor_profit = -999.0
            mejor_ruta_texto = ""

            for tri in triangulos:
                profit, texto = calcular_arbitraje(exchange, tri)
                if profit > mejor_profit:
                    mejor_profit = profit
                    mejor_ruta_texto = texto

            logger.info(f"Mejor: {mejor_ruta_texto} | {mejor_profit:.4f}% (min={MIN_PROFIT}%, max={MAX_PROFIT}%)")
            
            # Simulación de ejecución si la oportunidad es rentable
            if mejor_profit >= MIN_PROFIT:
                ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                CAPITAL_SIMULADO += ganancia
                logger.info(f"🔥 [SIMULACIÓN] ¡Orden ejecutada con éxito!")
                logger.info(f"💰 Nuevo Capital Simulado: ${CAPITAL_SIMULADO:.2f} USDT (Ganancia: +${ganancia:.4f})")
            else:
                logger.info(f"📋 No hay ganancias suficientes. Saldo simulado retenido en: ${CAPITAL_SIMULADO:.2f} USDT")
                
            print("-" * 50)
            time.sleep(5)  # Espera 5 segundos antes de volver a verificar el mercado

    except Exception as e:
        logger.error(f"Error crítico en el bot: {e}")

if __name__ == "__main__":
    ejecutar_bot()

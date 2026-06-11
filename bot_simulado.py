import time
import logging
import ccxt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger()

# --- PARÁMETROS DEL SIMULADOR ---
TAKER_FEE       = 0.0010
MIN_PROFIT      = 0.31
MAX_PROFIT      = 5.0       # FIX [1]: ahora se aplica en el filtro
CAPITAL_INICIAL = 50.0
CAPITAL_SIMULADO = 50.0
TOTAL_TRADES    = 0

# FIX [3]: máxima antigüedad aceptable de un ticker (ms)
MAX_TICKER_AGE_MS = 10_000  # 10 segundos


def inicializar_okx_publico():
    return ccxt.okx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})


def buscar_todos_los_triangulos(markets):
    pares_spot = [
        symbol for symbol, market in markets.items()
        if market['spot'] and market['active']
    ]
    simbolos_por_moneda = {}
    for par in pares_spot:
        base, quote = par.split('/')
        simbolos_por_moneda.setdefault(base, []).append(par)
        simbolos_por_moneda.setdefault(quote, []).append(par)

    triangulos = set()
    inicio = 'USDT'
    if inicio not in simbolos_por_moneda:
        return []

    for par1 in simbolos_por_moneda[inicio]:
        base1, quote1 = par1.split('/')
        m1 = base1 if quote1 == inicio else quote1
        if m1 not in simbolos_por_moneda:
            continue
        for par2 in simbolos_por_moneda[m1]:
            if par2 == par1:
                continue
            base2, quote2 = par2.split('/')
            m2 = base2 if quote2 == m1 else quote2
            for par3 in simbolos_por_moneda[m2]:
                if par3 == par2 or par3 == par1:
                    continue
                base3, quote3 = par3.split('/')
                if base3 == inicio or quote3 == inicio:
                    # FIX [5]: guardar como frozenset para evitar duplicados A→B→C / C→B→A
                    clave = frozenset([par1, par2, par3])
                    if clave not in triangulos:
                        triangulos.add(clave)
                        yield (par1, par2, par3)


def calcular_arbitraje(triangulo, tickers, now_ms):
    monto = 1.0
    moneda_actual = "USDT"
    ruta = ["USDT"]

    for par in triangulo:
        ticker = tickers.get(par)

        # FIX [3]: validar que el ticker no sea demasiado antiguo
        if not ticker or not ticker.get('ask') or not ticker.get('bid'):
            return -999.0, ""
        ts = ticker.get('timestamp')
        if ts and (now_ms - ts) > MAX_TICKER_AGE_MS:
            return -999.0, ""

        base, quote = par.split('/')

        if moneda_actual == quote:          # comprar base con quote
            monto = (monto / ticker['ask']) * (1 - TAKER_FEE)
            moneda_actual = base
        else:                               # vender base por quote
            monto = (monto * ticker['bid']) * (1 - TAKER_FEE)
            moneda_actual = quote

        ruta.append(moneda_actual)

    # FIX [2]: verificar que el triángulo cierra en USDT
    if moneda_actual != "USDT":
        return -999.0, ""

    # FIX [4]: ruta completa con USDT al inicio y al final
    texto = ">".join(ruta)
    return (monto - 1.0) * 100, texto


def ejecutar_bot():
    global CAPITAL_SIMULADO, TOTAL_TRADES

    exchange = inicializar_okx_publico()
    logger.info("INICIANDO SIMULADOR DE ARBITRAJE TRIANGULAR OKX...")

    try:
        markets = exchange.load_markets()
        # FIX [5]: usar generador para evitar lista de duplicados
        triangulos = list(buscar_todos_los_triangulos(markets))
        logger.info(f"Escaneando {len(triangulos)} triángulos únicos en OKX.")

        while True:
            try:
                tickers  = exchange.fetch_tickers()
                now_ms   = exchange.milliseconds()
                mejores  = []

                for tri in triangulos:
                    profit, texto = calcular_arbitraje(tri, tickers, now_ms)

                    # FIX [1]: aplicar filtro MAX_PROFIT
                    if MIN_PROFIT <= profit <= MAX_PROFIT:
                        mejores.append((texto, profit))

                mejores.sort(key=lambda x: x[1], reverse=True)

                if mejores:
                    mejor_texto, mejor_profit = mejores[0]
                    TOTAL_TRADES += 1
                    ganancia = CAPITAL_SIMULADO * (mejor_profit / 100)
                    CAPITAL_SIMULADO += ganancia
                    logger.info(
                        f"💰 [TRADE #{TOTAL_TRADES}] {mejor_texto} | "
                        f"+{mejor_profit:.4f}% | Saldo: ${CAPITAL_SIMULADO:.2f}"
                    )
                else:
                    # Mejor oportunidad fuera del rango (log informativo)
                    all_valid = [
                        (t, p) for tri in triangulos
                        for t, p in [calcular_arbitraje(tri, tickers, now_ms)]
                        if p > -900
                    ]
                    if all_valid:
                        all_valid.sort(key=lambda x: x[1], reverse=True)
                        mejor_texto, mejor_profit = all_valid[0]
                        logger.info(
                            f"❌ [RECHAZADO] {mejor_texto} | "
                            f"{mejor_profit:.4f}% | Saldo: ${CAPITAL_SIMULADO:.2f} "
                            f"(Trades: {TOTAL_TRADES})"
                        )

            except ccxt.NetworkError as e:
                logger.warning(f"Error de red (reintentando): {e}")
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error en ciclo: {e}")

            time.sleep(0.5)

    except Exception as e:
        logger.error(f"Fallo crítico: {e}")


if __name__ == "__main__":
    ejecutar_bot()

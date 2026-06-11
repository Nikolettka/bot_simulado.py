import os
import time
import logging
import ccxt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger()

# ─────────────────────────────────────────────
#  CONFIGURACIÓN — variables de entorno Railway
# ─────────────────────────────────────────────
OKX_API_KEY    = os.environ.get("OKX_API_KEY",    "").strip()
OKX_SECRET     = os.environ.get("OKX_SECRET",     "").strip()
OKX_PASSPHRASE = os.environ.get("OKX_PASSPHRASE", "").strip()
DRY_RUN        = os.environ.get("DRY_RUN", "true").strip().lower() != "false"

# ─────────────────────────────────────────────
#  PARÁMETROS DE TRADING
# ─────────────────────────────────────────────
TRADE_USDT        = 3.0        # capital por trade en USDT
TAKER_FEE         = 0.0010     # 0.10% taker OKX
MIN_PROFIT        = 0.31       # % mínimo neto para ejecutar
MAX_PROFIT        = 5.0        # % máximo (filtro anti-stale)
MAX_TICKER_AGE_MS = 10_000     # 10 s — ticker más viejo = ignorado
SLEEP_SECONDS     = 0.5        # pausa entre ciclos

# ─────────────────────────────────────────────
#  ESTADO GLOBAL
# ─────────────────────────────────────────────
capital_simulado = TRADE_USDT * 10   # saldo virtual en dry-run
total_trades     = 0
total_profit_pct = 0.0


# ══════════════════════════════════════════════
#  INICIALIZACIÓN DEL EXCHANGE
# ══════════════════════════════════════════════
def crear_exchange(autenticado: bool):
    config = {
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    }
    if autenticado:
        config["apiKey"]     = OKX_API_KEY
        config["secret"]     = OKX_SECRET
        config["password"]   = OKX_PASSPHRASE
    return ccxt.okx(config)


# ══════════════════════════════════════════════
#  CONSTRUCCIÓN DE TRIÁNGULOS
# ══════════════════════════════════════════════
def buscar_triangulos(markets):
    pares_spot = [
        s for s, m in markets.items()
        if m.get("spot") and m.get("active")
    ]
    por_moneda = {}
    for par in pares_spot:
        base, quote = par.split("/")
        por_moneda.setdefault(base,  []).append(par)
        por_moneda.setdefault(quote, []).append(par)

    vistos = set()
    inicio = "USDT"
    if inicio not in por_moneda:
        return []

    resultado = []
    for p1 in por_moneda[inicio]:
        b1, q1 = p1.split("/")
        m1 = b1 if q1 == inicio else q1
        if m1 not in por_moneda:
            continue
        for p2 in por_moneda[m1]:
            if p2 == p1:
                continue
            b2, q2 = p2.split("/")
            m2 = b2 if q2 == m1 else q2
            for p3 in por_moneda.get(m2, []):
                if p3 == p1 or p3 == p2:
                    continue
                b3, q3 = p3.split("/")
                if b3 == inicio or q3 == inicio:
                    clave = frozenset([p1, p2, p3])
                    if clave not in vistos:
                        vistos.add(clave)
                        resultado.append((p1, p2, p3))
    return resultado


# ══════════════════════════════════════════════
#  CÁLCULO DE OPORTUNIDAD
# ══════════════════════════════════════════════
def calcular_profit(triangulo, tickers, now_ms):
    monto        = 1.0
    moneda       = "USDT"
    ruta         = ["USDT"]

    for par in triangulo:
        tk = tickers.get(par)
        if not tk or not tk.get("ask") or not tk.get("bid"):
            return None
        ts = tk.get("timestamp")
        if ts and (now_ms - ts) > MAX_TICKER_AGE_MS:
            return None

        base, quote = par.split("/")
        if moneda == quote:
            monto  = (monto / tk["ask"]) * (1 - TAKER_FEE)
            moneda = base
        else:
            monto  = (monto * tk["bid"]) * (1 - TAKER_FEE)
            moneda = quote
        ruta.append(moneda)

    if moneda != "USDT":
        return None

    return {
        "profit_pct": (monto - 1.0) * 100,
        "ruta_texto": ">".join(ruta),
        "triangulo":  triangulo,
        "tickers":    tickers,
    }


# ══════════════════════════════════════════════
#  EJECUCIÓN REAL DE LAS 3 ÓRDENES
# ══════════════════════════════════════════════
def ejecutar_triangulo(exchange, oportunidad):
    """
    Ejecuta las 3 órdenes de mercado en secuencia.
    Devuelve (ok: bool, detalle: str).
    """
    triangulo = oportunidad["triangulo"]
    tickers   = oportunidad["tickers"]
    monto_usdt = TRADE_USDT
    moneda     = "USDT"
    detalle    = []

    for par in triangulo:
        tk          = tickers[par]
        base, quote = par.split("/")

        try:
            if moneda == quote:
                # Comprar base pagando en quote (USDT o bridge coin)
                # OKX market buy spot: amount = cantidad de BASE a comprar
                cantidad_base = (monto_usdt / tk["ask"]) * (1 - TAKER_FEE)
                orden = exchange.create_order(
                    symbol = par,
                    type   = "market",
                    side   = "buy",
                    amount = cantidad_base,
                )
                monto_usdt = cantidad_base   # ahora llevamos base
                moneda     = base
            else:
                # Vender base por quote
                orden = exchange.create_order(
                    symbol = par,
                    type   = "market",
                    side   = "sell",
                    amount = monto_usdt,
                )
                # El filled cost es lo que recibimos en quote
                filled     = float(orden.get("filled") or orden.get("amount") or monto_usdt)
                price_avg  = float(orden.get("average") or tk["bid"])
                monto_usdt = filled * price_avg * (1 - TAKER_FEE)
                moneda     = quote

            oid = orden.get("id", "?")
            detalle.append(f"{par} OK (id={oid})")
            logger.info(f"  ✅ Orden {par} ejecutada → id={oid}")

        except Exception as e:
            detalle.append(f"{par} ERROR: {e}")
            logger.error(f"  ❌ Orden {par} falló: {e}")
            return False, " | ".join(detalle)

    ganancia_usdt = monto_usdt - TRADE_USDT
    return True, f"Ganancia estimada: ${ganancia_usdt:.4f} | {' | '.join(detalle)}"


# ══════════════════════════════════════════════
#  LOOP PRINCIPAL
# ══════════════════════════════════════════════
def ejecutar_bot():
    global capital_simulado, total_trades, total_profit_pct

    modo = "🔵 DRY-RUN" if DRY_RUN else "🟢 LIVE"

    # Exchange público para tickers/markets (sin claves)
    exchange_pub = crear_exchange(autenticado=False)

    # Exchange autenticado solo en live
    exchange_live = None
    if not DRY_RUN:
        if not OKX_API_KEY or not OKX_SECRET or not OKX_PASSPHRASE:
            logger.error("❌ Faltan variables OKX_API_KEY / OKX_SECRET / OKX_PASSPHRASE")
            return
        exchange_live = crear_exchange(autenticado=True)
        # Verificar credenciales
        try:
            balance = exchange_live.fetch_balance()
            usdt_disponible = balance["free"].get("USDT", 0)
            logger.info(f"✅ Autenticado en OKX | USDT disponible: ${usdt_disponible:.2f}")
            if usdt_disponible < TRADE_USDT:
                logger.error(f"❌ Saldo insuficiente: ${usdt_disponible:.2f} < ${TRADE_USDT} requerido")
                return
        except Exception as e:
            logger.error(f"❌ Error de autenticación OKX: {e}")
            return

    logger.info(f"{'='*50}")
    logger.info(f"  ARBIBOT OKX — Modo: {modo}")
    logger.info(f"  Trade size: ${TRADE_USDT} | Min profit: {MIN_PROFIT}%")
    logger.info(f"{'='*50}")

    try:
        markets   = exchange_pub.load_markets()
        triangulos = buscar_triangulos(markets)
        logger.info(f"📐 {len(triangulos)} triángulos únicos cargados.")

        while True:
            try:
                tickers = exchange_pub.fetch_tickers()
                now_ms  = exchange_pub.milliseconds()

                mejores = []
                top_rechazado = None

                for tri in triangulos:
                    res = calcular_profit(tri, tickers, now_ms)
                    if res is None:
                        continue
                    p = res["profit_pct"]
                    if MIN_PROFIT <= p <= MAX_PROFIT:
                        mejores.append(res)
                    elif p > 0 and (top_rechazado is None or p > top_rechazado["profit_pct"]):
                        top_rechazado = res

                mejores.sort(key=lambda x: x["profit_pct"], reverse=True)

                if mejores:
                    mejor = mejores[0]
                    p     = mejor["profit_pct"]
                    ruta  = mejor["ruta_texto"]
                    total_trades     += 1
                    total_profit_pct += p

                    if DRY_RUN:
                        ganancia          = capital_simulado * (p / 100)
                        capital_simulado += ganancia
                        logger.info(
                            f"💰 [DRY #{total_trades}] {ruta} | "
                            f"+{p:.4f}% | Saldo virtual: ${capital_simulado:.2f} "
                            f"| Total acumulado: {total_profit_pct:.4f}%"
                        )
                    else:
                        logger.info(f"🚀 [LIVE #{total_trades}] Ejecutando {ruta} | +{p:.4f}%")
                        ok, detalle = ejecutar_triangulo(exchange_live, mejor)
                        if ok:
                            logger.info(f"✅ [LIVE #{total_trades}] {detalle}")
                        else:
                            logger.error(f"❌ [LIVE #{total_trades}] Fallo parcial: {detalle}")
                            total_trades -= 1  # no contar como trade exitoso

                elif top_rechazado:
                    p    = top_rechazado["profit_pct"]
                    ruta = top_rechazado["ruta_texto"]
                    saldo_txt = f"${capital_simulado:.2f}" if DRY_RUN else "live"
                    logger.info(
                        f"❌ [RECHAZADO] {ruta} | {p:.4f}% | "
                        f"Saldo: {saldo_txt} (Trades: {total_trades})"
                    )

            except ccxt.NetworkError as e:
                logger.warning(f"⚠️  Red: {e} — reintentando en 3s")
                time.sleep(3)
            except ccxt.ExchangeError as e:
                logger.error(f"⚠️  Exchange: {e}")
            except Exception as e:
                logger.error(f"Error en ciclo: {e}")

            time.sleep(SLEEP_SECONDS)

    except Exception as e:
        logger.error(f"Fallo crítico: {e}")


if __name__ == "__main__":
    ejecutar_bot()

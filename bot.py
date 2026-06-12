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
TRADE_USDT        = 3.0
TAKER_FEE         = 0.0010
MIN_PROFIT        = 0.31
MAX_PROFIT        = 5.0
MAX_TICKER_AGE_MS = 10_000
SLEEP_SECONDS     = 3.0   # OPT-1: 3s en vez de 2s — ahorra ~33% CPU/crédito

# OPT-2: Solo 10 bridges core — menos triángulos, menos RAM, mismas oportunidades reales
BRIDGE_COINS = {"BTC", "ETH", "SOL", "XRP", "DOGE", "OKB", "LTC", "ADA", "AVAX", "TON"}

# ─────────────────────────────────────────────
#  ESTADO GLOBAL
# ─────────────────────────────────────────────
capital_simulado = TRADE_USDT * 10
total_trades     = 0
total_profit_pct = 0.0


# ══════════════════════════════════════════════
#  INICIALIZACIÓN
# ══════════════════════════════════════════════
def crear_exchange(autenticado: bool):
    cfg = {"enableRateLimit": True, "options": {"defaultType": "spot"}}
    if autenticado:
        cfg["apiKey"]   = OKX_API_KEY
        cfg["secret"]   = OKX_SECRET
        cfg["password"] = OKX_PASSPHRASE
    return ccxt.okx(cfg)


# ══════════════════════════════════════════════
#  CONSTRUCCIÓN DE TRIÁNGULOS + ÍNDICE DE PARES
# ══════════════════════════════════════════════
def buscar_triangulos(markets):
    """Devuelve (lista_triangulos, set_pares_necesarios)."""
    pares_spot = [s for s, m in markets.items() if m.get("spot") and m.get("active")]
    por_moneda = {}
    for par in pares_spot:
        b, q = par.split("/")
        por_moneda.setdefault(b, []).append(par)
        por_moneda.setdefault(q, []).append(par)

    vistos    = set()
    resultado = []
    inicio    = "USDT"
    if inicio not in por_moneda:
        return [], set()

    for p1 in por_moneda[inicio]:
        b1, q1 = p1.split("/")
        m1 = b1 if q1 == inicio else q1
        if m1 not in BRIDGE_COINS or m1 not in por_moneda:
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

    # OPT-3: índice de todos los pares que necesitamos — para fetch selectivo
    pares_necesarios = set()
    for tri in resultado:
        pares_necesarios.update(tri)

    return resultado, pares_necesarios


# ══════════════════════════════════════════════
#  FETCH SELECTIVO — solo los pares del triángulo
# ══════════════════════════════════════════════
def fetch_tickers_selectivo(exchange, pares):
    """
    OPT-3: En vez de fetch_tickers() (descarga ~600 pares),
    descargamos solo los ~40 pares que usamos.
    Ahorra ~93% de ancho de banda y RAM por ciclo.
    """
    result = {}
    # ccxt permite pasar lista de symbols a fetch_tickers en OKX
    try:
        data = exchange.fetch_tickers(list(pares))
        return data
    except Exception:
        # fallback: fetch uno a uno si el exchange no soporta lista
        for par in pares:
            try:
                t = exchange.fetch_ticker(par)
                result[par] = t
            except Exception:
                pass
        return result


# ══════════════════════════════════════════════
#  CÁLCULO DE OPORTUNIDAD
# ══════════════════════════════════════════════
def calcular_profit(triangulo, tickers, now_ms):
    monto  = 1.0
    moneda = "USDT"
    ruta   = ["USDT"]

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
    triangulo  = oportunidad["triangulo"]
    tickers    = oportunidad["tickers"]
    monto_usdt = TRADE_USDT
    moneda     = "USDT"
    detalle    = []

    for par in triangulo:
        tk          = tickers[par]
        base, quote = par.split("/")
        try:
            if moneda == quote:
                cantidad_base = (monto_usdt / tk["ask"]) * (1 - TAKER_FEE)
                orden = exchange.create_order(par, "market", "buy", cantidad_base)
                monto_usdt = cantidad_base
                moneda     = base
            else:
                orden  = exchange.create_order(par, "market", "sell", monto_usdt)
                filled = float(orden.get("filled") or orden.get("amount") or monto_usdt)
                price  = float(orden.get("average") or tk["bid"])
                monto_usdt = filled * price * (1 - TAKER_FEE)
                moneda     = quote

            oid = orden.get("id", "?")
            detalle.append(f"{par} OK (id={oid})")
            logger.info(f"  ✅ {par} ejecutado → id={oid}")

        except Exception as e:
            detalle.append(f"{par} ERROR: {e}")
            logger.error(f"  ❌ {par} falló: {e}")
            return False, " | ".join(detalle)

    ganancia = monto_usdt - TRADE_USDT
    return True, f"Ganancia: ${ganancia:.4f} | {' | '.join(detalle)}"


# ══════════════════════════════════════════════
#  LOOP PRINCIPAL
# ══════════════════════════════════════════════
def ejecutar_bot():
    global capital_simulado, total_trades, total_profit_pct

    modo = "🔵 DRY-RUN" if DRY_RUN else "🟢 LIVE"
    exchange_pub  = crear_exchange(autenticado=False)
    exchange_live = None

    if not DRY_RUN:
        if not OKX_API_KEY or not OKX_SECRET or not OKX_PASSPHRASE:
            logger.error("❌ Faltan OKX_API_KEY / OKX_SECRET / OKX_PASSPHRASE")
            return
        exchange_live = crear_exchange(autenticado=True)
        try:
            balance = exchange_live.fetch_balance()
            usdt    = balance["free"].get("USDT", 0)
            logger.info(f"✅ OKX autenticado | USDT libre: ${usdt:.2f}")
            if usdt < TRADE_USDT:
                logger.error(f"❌ Saldo insuficiente: ${usdt:.2f} < ${TRADE_USDT}")
                return
        except Exception as e:
            logger.error(f"❌ Auth OKX: {e}")
            return

    logger.info("=" * 50)
    logger.info(f"  ARBIBOT OKX — {modo}")
    logger.info(f"  Trade: ${TRADE_USDT} | Min: {MIN_PROFIT}% | Sleep: {SLEEP_SECONDS}s")
    logger.info("=" * 50)

    try:
        markets              = exchange_pub.load_markets()
        triangulos, pares_ok = buscar_triangulos(markets)
        logger.info(f"📐 {len(triangulos)} triángulos | {len(pares_ok)} pares únicos")

        # OPT-3: liberar markets de memoria — ya no se necesita
        del markets

        while True:
            try:
                # OPT-3: fetch selectivo — solo los pares que usamos
                tickers = fetch_tickers_selectivo(exchange_pub, pares_ok)
                now_ms  = exchange_pub.milliseconds()

                mejores       = []
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
                            f"💰 [DRY #{total_trades}] {ruta} | +{p:.4f}% | "
                            f"Saldo: ${capital_simulado:.2f} | Acum: {total_profit_pct:.4f}%"
                        )
                    else:
                        logger.info(f"🚀 [LIVE #{total_trades}] {ruta} | +{p:.4f}%")
                        ok, det = ejecutar_triangulo(exchange_live, mejor)
                        if ok:
                            logger.info(f"✅ [LIVE #{total_trades}] {det}")
                        else:
                            logger.error(f"❌ [LIVE #{total_trades}] {det}")
                            total_trades -= 1

                elif top_rechazado:
                    p    = top_rechazado["profit_pct"]
                    ruta = top_rechazado["ruta_texto"]
                    saldo = f"${capital_simulado:.2f}" if DRY_RUN else "live"
                    logger.info(
                        f"❌ [RECHAZADO] {ruta} | {p:.4f}% | "
                        f"Saldo: {saldo} (Trades: {total_trades})"
                    )

                # OPT-3: limpiar tickers de memoria después de usarlos
                del tickers

            except ccxt.NetworkError as e:
                logger.warning(f"⚠️  Red: {e} — reintentando en 5s")
                time.sleep(5)
            except ccxt.ExchangeError as e:
                logger.error(f"⚠️  Exchange: {e}")
            except Exception as e:
                logger.error(f"Error ciclo: {e}")

            time.sleep(SLEEP_SECONDS)

    except Exception as e:
        logger.error(f"Fallo crítico: {e}")


if __name__ == "__main__":
    ejecutar_bot()

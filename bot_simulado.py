<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OKX ARBITRAGE PRO</title>
    <script src="https://socket.io"></script>
    <style>
        body { background-color: #12161a; color: #ffffff; font-family: sans-serif; padding: 12px; margin: 0; }
        .card { background-color: #1e232a; border-radius: 12px; padding: 15px; margin-top: 12px; }
        .grid { display: flex; gap: 10px; margin-top: 12px; }
        .col { flex: 1; background-color: #1e232a; border-radius: 12px; padding: 12px; text-align: center; }
        .label { color: #848e9c; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
        .value { font-size: 16px; font-weight: bold; margin-top: 4px; }
        .btn { display: inline-block; color: white; padding: 10px 30px; border-radius: 8px; font-weight: bold; text-decoration: none; margin-top: 10px; transition: background-color 0.2s; border: none; cursor: pointer; }
    </style>
</head>
<body>
    <h2 style="text-align:center;color:#eaecef;border-bottom:1px solid #2b3139;padding-bottom:10px;margin:0;">⚡ OKX ARBITRAGE ULTRA PRO</h2>
    
    <div class="card" style="text-align:center;">
        <div class="label">Estado del Sistema</div>
        <div id="est_texto" style="font-size:15px; font-weight:bold; margin-top:5px;">Cargando...</div>
        <button id="btn_motor" class="btn" onclick="toggleMotor()">... MOTOR</button>
    </div>

    <div class="card" style="text-align:center;">
        <div class="label">Capital Simulado Disponible</div>
        <div id="capital" style="color:#02c076;font-size:34px;font-weight:bold;margin-top:3px;">$0.00 USDT</div>
        <div style="display:flex; justify-content:space-between; margin-top:10px; font-size:12px; border-top:1px solid #2b3139; padding-top:8px;">
            <div><span class="label">Neto ganado:</span> <b id="neto" style="color:#02c076;">$0.00</b></div>
            <div><span class="label">Trades Exitosos:</span> <b id="trades_count" style="color:#f0b90b;">0</b></div>
        </div>
    </div>
    
    <div class="grid">
        <div class="col">
            <div class="label">Spread Máximo</div>
            <div id="profit" class="value">0.00%</div>
        </div>
        <div class="col">
            <div class="label">Filtro Mínimo</div>
            <div id="min_p" class="value" style="color:#f0b90b;">+0.3%</div>
        </div>
    </div>

    <div class="card">
        <div class="label" style="margin-bottom:8px;font-weight:bold;color:#eaecef;">🔥 Top 3 Caminos y Precios Libros OKX</div>
        <div id="top_3">Cargando rutas del mercado...</div>
    </div>

    <div class="card">
        <div class="label" style="margin-bottom:6px;font-weight:bold;color:#eaecef;">📊 Historial de Rangos y Gastos de Operación</div>
        <div style="display:flex;justify-content:space-between;font-size:12px; margin-bottom:5px;">
            <div><span class="label">Max:</span> <b id="r_max" style="color:#02c076;">0.00%</b></div>
            <div><span class="label">Min:</span> <b id="r_min" style="color:#f84960;">0.00%</b></div>
        </div>
        <div style="font-size:12px; border-top:1px solid #2b3139; padding-top:5px;">
            <span class="label">Fees Estimados (Ruta):</span> <b id="comision" style="color:#f84960;">$0.00 USDT</b>
        </div>
    </div>

    <div class="card">
        <div class="label" style="margin-bottom:8px;font-weight:bold;color:#eaecef;">⚙️ Telemetría, Tráfico de Red y Enlace</div>
        <div style="font-size:12px; display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-bottom:5px;">
            <div><span class="label">Conexión API:</span> <b id="conexion">...</b></div>
            <div><span class="label">Reloj Bot:</span> <b id="hora">00:00:00</b></div>
            <div><span class="label">Rutas:</span> <b id="rutas">0</b></div>
            <div><span class="label">Latencia:</span> <b id="latencia">0.00s</b></div>
            <div><span class="label">Peso API:</span> b id="peso">0.0 KB</b></div>
            <div><span class="label">Total Red:</span> <b id="total_r">0.00 MB</b></div>
        </div>
    </div>

    <div class="card">
        <div class="label" style="border-bottom:1px solid #2b3139;padding-bottom:6px;margin-bottom:8px;font-weight:bold;color:#eaecef;">📜 Registro de Operaciones Exitosas</div>
        <div id="trades_lista">Esperando oportunidades...</div>
    </div>

    <script>
        const socket = io();

        socket.on('update_data', function(data) {
            document.getElementById('capital').innerHTML = data.capital;
            document.getElementById('neto').innerHTML = data.neto;
            document.getElementById('trades_count').innerHTML = data.trades;
            document.getElementById('conexion').innerHTML = data.conexion;
            document.getElementById('profit').innerHTML = data.profit;
            document.getElementById('profit').style.color = data.color_p;
            document.getElementById('min_p').innerHTML = data.min_p;
            document.getElementById('comision').innerHTML = data.comision;
            document.getElementById('top_3').innerHTML = data.top_3;
            document.getElementById('r_max').innerHTML = data.r_max;
            document.getElementById('r_min').innerHTML = data.r_min;
            document.getElementById('rutas').innerHTML = data.rutas;
            document.getElementById('latencia').innerHTML = data.latencia;
            document.getElementById('peso').innerHTML = data.peso;
            document.getElementById('total_r').innerHTML = data.total_r;
            document.getElementById('trades_lista').innerHTML = data.trades_lista;
            document.getElementById('hora').innerHTML = data.hora;
            
            const btn = document.getElementById('btn_motor');
            btn.innerHTML = data.btn_texto + " MOTOR";
            btn.style.backgroundColor = data.btn_color;
            
            const est = document.getElementById('est_texto');
            est.innerHTML = data.est_texto;
            est.style.color = data.est_color;
        });

        function toggleMotor() {
            fetch('/toggle');
        }
    </script>
</body>
</html>

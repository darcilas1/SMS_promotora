import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

import requests
from dotenv import load_dotenv

# Cargar variables de entorno (.env)
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
python_exe = sys.executable  # usa el python del venv activo

# Lista de procesos en orden de ejecución.
# Cada tupla: (nombre, ruta, critico)
# critico=False → si falla, se registra pero NO se detiene la cadena.
PROCESOS = [
    ("Descargue Multicanal", BASE_DIR / "RPA_descargue_multicanal.py", False),
    ("Procesamiento SMS",    BASE_DIR / "main_sms.py",                  True),
    ("Cargue Promotora",    BASE_DIR / "RPA_cargue.py",                 True),
]

LOGS_DIR = BASE_DIR / "logs_orquestador"
LOGS_DIR.mkdir(exist_ok=True)

TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL")

def log(msg: str):
    """Escribe log en consola y en archivo de log diario."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)

    log_file = LOGS_DIR / f"orquestador_{datetime.now().strftime('%Y%m%d')}.log"
    with log_file.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def notificar_teams_resumen(exitosos: list[str], fallidos: list[str]):
    """Envía a Teams un resumen final de la ejecución del orquestador principal."""
    if not TEAMS_WEBHOOK_URL:
        log("⚠ TEAMS_WEBHOOK_URL no configurado. No se enviará resumen a Teams.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(exitosos) + len(fallidos)

    lineas = [
        "📊 *Resumen de ejecución RPA – PROMOTORA*",
        "",
        f"**Fecha/Hora:** {timestamp}",
        f"**Total procesos:** {total}",
        f"**Exitosos:** {len(exitosos)}",
        f"**Fallidos / Detenidos:** {len(fallidos)}",
        "",
    ]

    if exitosos:
        lineas.append("✅ **Procesos exitosos:**")
        lineas.append("\n".join(f"- {nombre}" for nombre in exitosos))
        lineas.append("")

    if fallidos:
        lineas.append("❌ **Procesos fallidos o no ejecutados:**")
        lineas.append("\n".join(f"- {nombre}" for nombre in fallidos))
        lineas.append("")
        lineas.append("_Revisar logs locales del orquestador para más detalle._")

    payload = {"text": "\n".join(lineas)}

    try:
        resp = requests.post(TEAMS_WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code != 200:
            log(f"❌ Error al enviar resumen a Teams. Status: {resp.status_code}, Resp: {resp.text}")
        else:
            log("📨 Resumen de ejecución enviado a Teams exitosamente.")
    except requests.RequestException as e:
        log(f"❌ Excepción al enviar resumen a Teams: {e}")

def ejecutar_proceso(nombre: str, ruta: Path) -> bool:
    log(f"▶ Iniciando proceso: {nombre} ({ruta.name})")

    if not ruta.exists():
        msg = f"ERROR: el archivo no existe: {ruta}"
        log(f"❌ {msg}")
        return False

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [python_exe, str(ruta)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )

    if result.returncode != 0:
        detalle = f"Código de salida: {result.returncode}"
        log(f"❌ ERROR en {nombre}. {detalle}")
        if result.stderr:
            log(f"STDERR:\n{result.stderr}")
        if result.stdout:
            log(f"STDOUT:\n{result.stdout}")
        return False

    log(f"✅ Proceso {nombre} finalizado correctamente.")
    if result.stdout:
        log(f"STDOUT:\n{result.stdout}")
    return True

def main():
    log(f"🚀 Iniciando orquestador Promotora con {len(PROCESOS)} procesos...")
    resultados = []

    for nombre, ruta, critico in PROCESOS:
        ok = ejecutar_proceso(nombre, ruta)
        resultados.append((nombre, ok))
        if not ok:
            if critico:
                log(f"⚠ Proceso crítico fallido: {nombre}. Abortando la ejecución secuencial...")
                break
            else:
                log(f"⚠ Proceso no crítico fallido: {nombre}. Continuando con el siguiente proceso...")

    exitosos = [n for n, ok in resultados if ok]
    fallidos = [n for n, ok in resultados if not ok]

    procesos_ejecutados = exitosos + fallidos
    no_ejecutados = [n for n, _, _ in PROCESOS if n not in procesos_ejecutados]
    for n in no_ejecutados:
        fallidos.append(f"{n} (Abor.)")

    log("📊 Resumen de ejecución (orquestador principal):")
    log(f"   ✅ Exitosos ({len(exitosos)}): {', '.join(exitosos) if exitosos else 'Ninguno'}")
    log(f"   ❌ Fallidos ({len(fallidos)}): {', '.join(fallidos) if fallidos else 'Ninguno'}")

    notificar_teams_resumen(exitosos, fallidos)

if __name__ == "__main__":
    main()

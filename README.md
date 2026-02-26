# 📲 RPA – Cargue de Gestiones SMS Promotora

Automatización para la preparación y cargue masivo de gestiones de **Mensajes de Texto (SMS)** al CRM del negocio **Promotora**. El proceso descarga el archivo multicanal desde el sistema interno, obtiene la base de SMS desde **AWS S3**, construye el archivo de gestiones en el formato requerido, lo divide en lotes y finalmente lo carga al CRM de forma secuencial.

---

## 📋 Tabla de Contenidos

- [Descripción General](#descripción-general)
- [Flujo del Proceso](#flujo-del-proceso)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Requisitos Previos](#requisitos-previos)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Ejecución](#ejecución)
- [Programación (Scheduler)](#programación-scheduler)
- [Logs y Monitoreo](#logs-y-monitoreo)
- [Notificaciones Teams](#notificaciones-teams)
- [Descripción de Scripts](#descripción-de-scripts)
- [Variables de Entorno](#variables-de-entorno)
- [Notas Importantes](#notas-importantes)

---

## 📌 Descripción General

Este RPA automatiza el proceso de cargue de gestiones de SMS para la cartera del negocio **Promotora**. El flujo completo es orquestado por `orquestacion.py`, que ejecuta tres subprocesos en secuencia estricta:

1. **Descargue Multicanal** – Descarga el reporte multicanal desde el CRM usando Selenium.
2. **Procesamiento SMS** – Descarga el archivo de SMS desde S3, construye el archivo de gestiones y lo divide en lotes de 20.000 registros.
3. **Cargue al CRM** – Sube los archivos generados al CRM mediante Selenium, lote por lote.

> ⚠️ Si alguno de los pasos falla, el orquestador **detiene la cadena** para evitar cargues con información desactualizada o errónea.

---

## 🔄 Flujo del Proceso

```
run_orquestador.bat
        │
        ▼
orquestacion.py  ──────────────────────────────────── notifica a Teams al finalizar
        │
        ├── 1️⃣ RPA_descargue_multicanal.py
        │       └── Selenium → Login CRM → Descarga reporte Multicanal (.csv)
        │               └── Guarda en: Multicanal/
        │
        ├── 2️⃣ main_sms.py
        │       ├── Lee el CSV más reciente de Multicanal/
        │       ├── Descarga el archivo SMS más reciente desde AWS S3
        │       │       (bucket: datos-vg/PROMOTORA/MASIVOS/)
        │       ├── Construye el archivo de gestiones con el formato del CRM
        │       ├── Guarda archivo completo en: Mensaje_Texto/cargue_sms_YYYY-MM-DD.csv
        │       ├── Divide en lotes de 20.000 filas → Mensaje_Texto/lotes/
        │       └── Mueve el archivo S3 procesado → PROCESADOS/
        │
        └── 3️⃣ RPA_cargue.py
                ├── Selenium → Login CRM → Selección campaña Promotora
                ├── Carga lotes SMS uno por uno (espera 3 min entre cada lote)
                └── Mueve archivos cargados → PROCESADOS/YYYY-MM-DD/
```

---

## 🗂️ Estructura del Proyecto

```
cargue_promotora/
│
├── orquestacion.py              # Orquestador principal – ejecuta los 3 subprocesos en secuencia
├── RPA_descargue_multicanal.py  # Descarga el reporte Multicanal desde el CRM (Selenium)
├── main_sms.py                  # Procesa el archivo SMS desde S3 y genera los lotes
├── RPA_cargue.py                # Carga los lotes al CRM (Selenium)
│
├── run_orquestador.bat          # Script de entrada – activa el venv y lanza orquestacion.py
├── requirements.txt             # Dependencias Python del proyecto
├── formatoArbolProducto.csv     # Plantilla con el formato de columnas requerido por el CRM
│
├── .env                         # Variables de entorno (NO se sube al repositorio)
├── .gitignore                   # Archivos y carpetas excluidas del control de versiones
│
├── Multicanal/                  # Carpeta donde se guardan los reportes descargados del CRM
│   └── *.csv
│
├── Mensaje_Texto/               # Carpeta donde se generan los archivos de gestiones SMS
│   ├── cargue_sms_YYYY-MM-DD.csv   # Archivo completo del día
│   ├── lotes/                       # Lotes de 20.000 registros para el cargue
│   │   ├── cargue_sms_2026-01-01_lote_001.csv
│   │   ├── cargue_sms_2026-01-01_lote_002.csv
│   │   └── ...
│   └── PROCESADOS/
│       └── YYYY-MM-DD/          # Lotes ya cargados al CRM
│
├── Logs/
│   └── cargues_log.csv          # Log detallado de cada cargue al CRM
│
├── logs_orquestador/
│   └── orquestador_YYYYMMDD.log # Log diario del orquestador principal
│
└── venv/                        # Entorno virtual Python (NO se sube al repositorio)
```

---

## ✅ Requisitos Previos

| Requisito | Versión recomendada |
|-----------|---------------------|
| Python | 3.10 o superior |
| Google Chrome | Última versión estable |
| ChromeDriver | Compatible con la versión de Chrome instalada |
| AWS CLI (opcional) | Credenciales configuradas en `.env` |
| Acceso CRM | Credenciales de usuario VG activas |

---

## 🚀 Instalación

### 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd cargue_promotora
```

### 2. Crear el entorno virtual

```bash
python -m venv venv
```

### 3. Activar el entorno virtual

```bash
# Windows
venv\Scripts\activate
```

### 4. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 5. Configurar el archivo `.env`

Copia el archivo de ejemplo y completa las variables (ver sección [Variables de Entorno](#variables-de-entorno)):

```bash
copy .env.example .env
```

---

## ⚙️ Configuración

### Archivo `.env`

Crea el archivo `.env` en la raíz del proyecto con el siguiente contenido:

```env
# Credenciales CRM (Vision Gerencial)
USERNAME_VG=tu_usuario
PASSWORD_VG=tu_contraseña

# AWS S3
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=tu_access_key
AWS_SECRET_ACCESS_KEY=tu_secret_key
S3_BUCKET=nombre-del-bucket

# Microsoft Teams Webhook (para notificaciones)
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/...
```

> ⚠️ **Nunca subas el archivo `.env` al repositorio.** Ya está incluido en `.gitignore`.

### Plantilla del CRM

El archivo `formatoArbolProducto.csv` contiene las columnas exactas que requiere el CRM para el cargue de gestiones. **No modificar** sin validar contra el sistema.

---

## ▶️ Ejecución

La forma estándar de ejecutar el proceso es a través del archivo `.bat`:

```bash
# Hacer doble click en Windows Explorer, o ejecutar desde CMD:
run_orquestador.bat
```

Este script:
1. Activa el entorno virtual `venv`
2. Ejecuta `orquestacion.py` con el Python del entorno

También puedes ejecutarlo manualmente con el entorno activado:

```bash
venv\Scripts\activate
python orquestacion.py
```

---

## ⏰ Programación (Scheduler)

El proceso se programa en el **Programador de Tareas de Windows** con la siguiente configuración:

| Día | Hora de ejecución |
|-----|-------------------|
| Lunes a Viernes | **5:00 PM** |
| Sábados | **2:00 PM** |

**Acción configurada en el Programador de Tareas:**
```
Programa:  C:\...\cargue_promotora\venv\Scripts\python.exe
Argumentos: orquestacion.py
Iniciar en: C:\...\cargue_promotora\
```

> 💡 También puede configurarse usando `run_orquestador.bat` como acción directa.

---

## 📊 Logs y Monitoreo

### Log del Orquestador

Ubicación: `logs_orquestador/orquestador_YYYYMMDD.log`

Registra el inicio, finalización y resultado de cada subproceso:

```
[2026-02-26 17:00:01] 🚀 Iniciando orquestador Promotora con 3 procesos...
[2026-02-26 17:00:01] ▶ Iniciando proceso: Descargue Multicanal (RPA_descargue_multicanal.py)
[2026-02-26 17:01:10] ✅ Proceso Descargue Multicanal finalizado correctamente.
[2026-02-26 17:01:11] ▶ Iniciando proceso: Procesamiento SMS (main_sms.py)
...
[2026-02-26 17:05:30] 📊 Resumen de ejecución (orquestador principal):
[2026-02-26 17:05:30]    ✅ Exitosos (3): Descargue Multicanal, Procesamiento SMS, Cargue Promotora
[2026-02-26 17:05:30]    ❌ Fallidos (0): Ninguno
```

### Log de Cargues CRM

Ubicación: `Logs/cargues_log.csv` (separado por `;`)

| Campo | Descripción |
|-------|-------------|
| `timestamp` | Fecha y hora del evento |
| `tipo` | Tipo de cargue (`SMS`, `PREDICTIVO`, `RPA`) |
| `archivo` | Nombre del archivo cargado |
| `status` | Estado (`ENVIADO`, `OK_TIMEWAIT`, `MOVIDO_PROCESADOS`, `ERROR`) |
| `detalle` | Información adicional del evento |

---

## 🔔 Notificaciones Teams

Al finalizar la ejecución, el orquestador envía un resumen al canal de **Microsoft Teams** configurado en `TEAMS_WEBHOOK_URL`:

```
📊 Resumen de ejecución RPA – PROMOTORA

Fecha/Hora: 2026-02-26 17:05:30
Total procesos: 3
Exitosos: 3
Fallidos / Detenidos: 0

✅ Procesos exitosos:
- Descargue Multicanal
- Procesamiento SMS
- Cargue Promotora
```

Si la variable `TEAMS_WEBHOOK_URL` no está configurada, la notificación se omite y se registra una advertencia en el log.

---

## 📝 Descripción de Scripts

### `orquestacion.py`
Orquestador principal. Ejecuta los 3 scripts en secuencia usando `subprocess`. Si un paso falla, detiene los siguientes y reporta el resultado a Teams.

### `RPA_descargue_multicanal.py`
Automatización con **Selenium** que:
- Hace login en el CRM (`visiong.iagree.co`)
- Navega a la campaña Promotora
- Descarga el reporte **Multicanal** en formato CSV
- Guarda el archivo en la carpeta `Multicanal/`

### `main_sms.py`
Script de procesamiento de datos que:
- Lee el CSV de Multicanal más reciente
- Descarga el archivo de SMS más reciente desde **AWS S3** (`datos-vg/PROMOTORA/MASIVOS/`)
- Construye el DataFrame con el formato exacto del CRM (columnas, fechas, codificación)
- Sanitiza los mensajes (elimina tildes, emojis y caracteres especiales)
- Guarda el archivo completo en `Mensaje_Texto/`
- Divide el archivo en **lotes de 20.000 registros** en `Mensaje_Texto/lotes/`
- Mueve el archivo S3 original a la carpeta `PROCESADOS/` dentro del bucket

### `RPA_cargue.py`
Automatización con **Selenium** que:
- Hace login en el CRM
- Navega a la sección de **Importar** de la campaña Promotora
- Carga cada lote SMS de forma secuencial con **espera fija de 3 minutos** entre lotes
- Mueve los archivos ya cargados a `Mensaje_Texto/lotes/PROCESADOS/YYYY-MM-DD/`
- Registra cada evento en `Logs/cargues_log.csv`

---

## 🔑 Variables de Entorno

| Variable | Descripción | Requerida |
|----------|-------------|-----------|
| `USERNAME_VG` | Usuario del CRM Vision Gerencial | ✅ Sí |
| `PASSWORD_VG` | Contraseña del CRM Vision Gerencial | ✅ Sí |
| `S3_BUCKET` | Nombre del bucket S3 que contiene los archivos SMS | ✅ Sí |
| `AWS_REGION` | Región de AWS (por defecto: `us-east-1`) | ⚠️ Opcional |
| `AWS_ACCESS_KEY_ID` | Clave de acceso AWS | ⚠️ Si no usa perfil IAM |
| `AWS_SECRET_ACCESS_KEY` | Secreto de acceso AWS | ⚠️ Si no usa perfil IAM |
| `TEAMS_WEBHOOK_URL` | URL del webhook de Teams para notificaciones | ⚠️ Opcional |

---

## ⚠️ Notas Importantes

- **Dependencia entre pasos:** Los 3 subprocesos son dependientes entre sí. Si `RPA_descargue_multicanal.py` falla, los pasos siguientes no se ejecutarán.
- **ChromeDriver:** Debe estar disponible en el `PATH` del sistema o en el mismo directorio del proyecto. Verificar compatibilidad con la versión de Chrome instalada.
- **Captcha CRM:** El CRM incluye un captcha visual simple que el script resuelve automáticamente. Si el CRM cambia el captcha, el script requerirá actualización.
- **Tamaño de lotes:** El tamaño de cada lote SMS es de **20.000 registros** (configurable en `main_sms.py` mediante la constante `LOTE_SIZE`).
- **Espera entre lotes:** El RPA de cargue espera **3 minutos fijos** después de cargar cada lote para darle tiempo al CRM de procesar.
- **Archivos procesados:** Los archivos no se eliminan; se mueven a carpetas `PROCESADOS/` tanto localmente como en S3.
- **Codificación:** Los archivos de cargue se generan en codificación `latin-1` con separador `;`, según el requerimiento del CRM.

---

## 🤝 Contacto y Mantenimiento

**Área:** Automatización y Tecnología – Vision Gerencial  
**Negocio:** Promotora  
**Proceso:** Cargue masivo de gestiones SMS al CRM

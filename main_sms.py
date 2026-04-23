import os
import sys
import re
import unicodedata
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from io import BytesIO

import boto3
import pandas as pd
from dotenv import load_dotenv

# ========================= Rutas / Constantes =========================

PROJECT_ROOT   = Path(__file__).resolve().parent

TEMPLATE_PATH  = PROJECT_ROOT / "formatoArbolProducto.csv"
MENSAJE_DIR    = PROJECT_ROOT / "Mensaje_Texto"

# Carpeta de lotes
LOTES_DIR      = MENSAJE_DIR / "lotes"
LOTE_SIZE      = 10000  # <- tamaño de cada lote

MULTICANAL_DIR = PROJECT_ROOT / "Multicanal"

S3_FOLDER              = "datos-vg/PROMOTORA/MASIVOS/"
S3_PROCESADOS_FOLDER   = "datos-vg/PROMOTORA/MASIVOS/PROCESADOS/"

CONSTANTES = {
    "ASESOR": "vigpromotora1",
    "CANAL": "COMUNICACION ESCRITA",
    "ESTADO CLIENTE": "Mensaje De Texto",
    "ESTADO CONTACTO": "SIN CONTACTO",
    "NIVEL1": "SIN CONTACTO",
    "NIVEL2": "Mensaje De Texto",
    "NIVEL3": "MENSAJE DE TEXTO",
    "NIVEL4": "SIN MOTIVO",
}

FORMATO_COLUMNS = [
    "CEDULA","NUMERO TELEFONO","MENSAJE","ASESOR","FECHA GESTION","CANAL",
    "ESTADO CLIENTE","ESTADO CONTACTO","NIVEL1","NIVEL2","NIVEL3","NIVEL4",
    "NIVEL5","NIVEL6","NIVEL7","NIVEL8","NIVEL9","NIVEL10","NUMERO PRODUCTO"
]

# Headers exactos
MULTI_COL_ID   = "Número Identificación"
MULTI_COL_PROD = "Numero producto"

SMS_COL_CED = "Cedula"
SMS_COL_TEL = "Telefono"
SMS_COL_MSG = "Guion"

# ========================= Utilidades =========================

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def read_template_columns(path: Path) -> list:
    df_hdr = pd.read_csv(path, nrows=0, sep=";", dtype=str, engine="python")
    cols = [c.strip() for c in df_hdr.columns if c and not str(c).lower().startswith("unnamed")]
    return cols

def extract_date_from_s3_key(key: str) -> datetime:
    filename = Path(key).name
    match = re.match(r"^(\d{2}-\d{2}-\d{4})\b", filename)
    if not match:
        raise ValueError(
            f"El archivo S3 no inicia con una fecha valida dd-mm-YYYY: {filename}"
        )

    try:
        return datetime.strptime(match.group(1), "%d-%m-%Y")
    except ValueError as exc:
        raise ValueError(f"La fecha del archivo S3 no es valida: {filename}") from exc

def bogota_8am_str(source_date: datetime) -> str:
    tz = ZoneInfo("America/Bogota")
    dt = datetime(source_date.year, source_date.month, source_date.day, 8, 0, 0, tzinfo=tz)
    return dt.strftime("%d/%m/%Y %H:%M:%S")

def pick_latest_local_csv(folder: Path) -> Path:
    files = [p for p in folder.glob("*.csv") if p.is_file()]
    if not files:
        raise FileNotFoundError(f"No se encontró ningún CSV en {folder}")
    return max(files, key=lambda p: p.stat().st_mtime)

def clean_cedula(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.str.replace(r"\.0$", "", regex=True)
    s = s.str.replace(" ", "", regex=False)
    return s

def sanitize_sms_text(text: str) -> str:
    """
    Limpieza para SMS / CRM:
    - elimina tildes y ñ
    - elimina ¿ ? ¡ !
    - elimina emojis y caracteres raros
    - deja solo texto seguro
    """
    if not isinstance(text, str):
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    text = re.sub(r"[¿¡]", "", text)
    text = re.sub(r"[^a-zA-Z0-9\s\.,;:\-_()]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text

def split_dataframe_to_csv_lotes(df: pd.DataFrame, base_output_file: Path, lotes_dir: Path, lote_size: int = 20000):
    """
    Divide df en lotes de 'lote_size' filas y los guarda como CSV con el mismo formato del output.
    Retorna lista de Paths generados.
    """
    ensure_dir(lotes_dir)

    total = len(df)
    if total == 0:
        return []

    stem = base_output_file.stem  # ej: cargue_sms_2026-02-21
    suffix = base_output_file.suffix  # .csv

    num_lotes = (total + lote_size - 1) // lote_size
    paths = []

    for i in range(num_lotes):
        start = i * lote_size
        end = min(start + lote_size, total)
        lote_df = df.iloc[start:end].copy()

        lote_name = f"{stem}_lote_{i+1:03d}{suffix}"
        lote_path = lotes_dir / lote_name

        lote_df.to_csv(lote_path, index=False, encoding="latin-1", sep=";")
        paths.append(lote_path)

    return paths

# ========================= S3 helpers =========================

def s3_client():
    load_dotenv()
    return boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))

def pick_latest_object(client, bucket: str, prefix: str, exclude_prefix: str = "") -> dict:
    resp = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    files = [
        o for o in resp.get("Contents", [])
        if not o["Key"].endswith("/")
        and (not exclude_prefix or not o["Key"].startswith(exclude_prefix))
    ]
    if not files:
        raise FileNotFoundError("No se encontraron archivos en S3")
    return max(files, key=lambda x: x["LastModified"])

def read_sms_csv_from_s3(client, bucket: str, key: str) -> pd.DataFrame:
    body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
    try:
        return pd.read_csv(BytesIO(body), sep="|", dtype=str, encoding="utf-8", engine="python")
    except UnicodeDecodeError:
        return pd.read_csv(BytesIO(body), sep="|", dtype=str, encoding="latin-1", engine="python")

def read_multicanal_local(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, sep=";", dtype=str, encoding="utf-8", engine="python")
    except UnicodeDecodeError:
        return pd.read_csv(path, sep=";", dtype=str, encoding="latin-1", engine="python")

def move_s3_object(client, bucket: str, src_key: str, dest_prefix: str) -> str:
    """
    Mueve (copy + delete) un objeto dentro del mismo bucket.
    Retorna el dest_key final.
    """
    if not dest_prefix.endswith("/"):
        dest_prefix += "/"

    filename = src_key.split("/")[-1]
    dest_key = f"{dest_prefix}{filename}"

    if src_key == dest_key or src_key.startswith(dest_prefix):
        return src_key

    client.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": src_key},
        Key=dest_key
    )

    client.delete_object(Bucket=bucket, Key=src_key)

    return dest_key

# ========================= Multicanal =========================

def build_multicanal_map(df: pd.DataFrame) -> pd.DataFrame:
    if MULTI_COL_ID not in df.columns or MULTI_COL_PROD not in df.columns:
        raise ValueError("Columnas requeridas no existen en Multicanal")

    tmp = df[[MULTI_COL_ID, MULTI_COL_PROD]].copy()
    tmp.columns = ["CEDULA", "NUMERO PRODUCTO"]

    tmp["CEDULA"] = clean_cedula(tmp["CEDULA"])
    tmp["NUMERO PRODUCTO"] = tmp["NUMERO PRODUCTO"].astype(str).str.strip().fillna("")

    tmp = tmp[tmp["CEDULA"].ne("")]
    tmp = tmp.drop_duplicates(subset=["CEDULA"], keep="last")

    return tmp

# ========================= Construcción =========================

def build_cargue_sms(df_sms: pd.DataFrame, multicanal_map: pd.DataFrame, fecha_gestion: str) -> pd.DataFrame:
    for col in [SMS_COL_CED, SMS_COL_TEL, SMS_COL_MSG]:
        if col not in df_sms.columns:
            raise ValueError(f"Falta columna {col} en SMS S3")

    base = pd.DataFrame({
        "CEDULA": clean_cedula(df_sms[SMS_COL_CED]),
        "NUMERO TELEFONO": df_sms[SMS_COL_TEL].astype(str).str.strip(),
        "MENSAJE": df_sms[SMS_COL_MSG].apply(sanitize_sms_text),
    })

    base = base.merge(multicanal_map, on="CEDULA", how="left")
    base["NUMERO PRODUCTO"] = base["NUMERO PRODUCTO"].fillna("")

    out = pd.DataFrame({
        "CEDULA": base["CEDULA"],
        "NUMERO TELEFONO": base["NUMERO TELEFONO"],
        "MENSAJE": base["MENSAJE"],
        "ASESOR": CONSTANTES["ASESOR"],
        "FECHA GESTION": fecha_gestion,
        "CANAL": CONSTANTES["CANAL"],
        "ESTADO CLIENTE": CONSTANTES["ESTADO CLIENTE"],
        "ESTADO CONTACTO": CONSTANTES["ESTADO CONTACTO"],
        "NIVEL1": CONSTANTES["NIVEL1"],
        "NIVEL2": CONSTANTES["NIVEL2"],
        "NIVEL3": CONSTANTES["NIVEL3"],
        "NIVEL4": CONSTANTES["NIVEL4"],
        "NIVEL5": "",
        "NIVEL6": "",
        "NIVEL7": "",
        "NIVEL8": "",
        "NIVEL9": "",
        "NIVEL10": "",
        "NUMERO PRODUCTO": base["NUMERO PRODUCTO"],
    })

    return out.fillna("")

def enforce_template_order(df: pd.DataFrame) -> pd.DataFrame:
    tpl_cols = read_template_columns(TEMPLATE_PATH)
    for col in tpl_cols:
        if col not in df.columns:
            df[col] = ""
    return df[tpl_cols]

# ========================= Main =========================

def main():
    load_dotenv()
    ensure_dir(MENSAJE_DIR)
    ensure_dir(LOTES_DIR)

    multicanal_file = pick_latest_local_csv(MULTICANAL_DIR)
    df_multi = read_multicanal_local(multicanal_file)
    multicanal_map = build_multicanal_map(df_multi)

    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        raise ValueError("Falta variable de entorno S3_BUCKET")

    client = s3_client()
    latest = pick_latest_object(client, bucket, S3_FOLDER, exclude_prefix=S3_PROCESADOS_FOLDER)
    source_date = extract_date_from_s3_key(latest["Key"])
    fecha_gestion = bogota_8am_str(source_date)
    output_file = MENSAJE_DIR / f"cargue_sms_{source_date.strftime('%Y-%m-%d')}.csv"

    df_sms = read_sms_csv_from_s3(client, bucket, latest["Key"])

    out = build_cargue_sms(df_sms, multicanal_map, fecha_gestion)
    out = enforce_template_order(out)

    # 1) Guardar archivo completo (como antes)
    out.to_csv(output_file, index=False, encoding="latin-1", sep=";")

    # 2) NUEVO: dividir en lotes de 20.000
    lote_paths = split_dataframe_to_csv_lotes(
        df=out,
        base_output_file=output_file,
        lotes_dir=LOTES_DIR,
        lote_size=LOTE_SIZE
    )

    # ✅ EN VEZ DE BORRAR: mover a PROCESADOS
    dest_key = move_s3_object(client, bucket, latest["Key"], S3_PROCESADOS_FOLDER)

    print(f"✅ Archivo generado correctamente: {output_file}")
    print(f"📊 Filas: {len(out)}")

    if lote_paths:
        print(f"🧩 Lotes generados en: {LOTES_DIR}")
        print(f"📦 Cantidad de lotes: {len(lote_paths)}")
        print(f"🗂️ Ejemplo primer lote: {lote_paths[0]}")
    else:
        print("🧩 No se generaron lotes (archivo vacío).")

    print(f"📦 S3 movido a: s3://{bucket}/{dest_key}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        sys.exit(2)

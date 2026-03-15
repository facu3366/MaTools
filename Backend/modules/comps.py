from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pathlib
import json
import os
import sys
import pandas as pd
import time
from datetime import datetime
import io
from fastapi.responses import StreamingResponse

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from financial_engine import (
    get_financials_ttm,
    build_comps_response
)

from comps_automatico import (
    generar_excel,
    _generar_excel_buffer,
    DEAL_CONFIG
)

router = APIRouter()

# ─────────────────────────────────────────────
# MODELO
# ─────────────────────────────────────────────

class CompsRequest(BaseModel):

    mensaje: str

    analista: str = "Analista"

    empresa_override: str = ""
    sector_override: str = ""
    revenue_override: float = 0

    moneda: str = "USD"
    escala: str = "mm"

    rango_min_pct: float = 30
    rango_max_pct: float = 300


# ─────────────────────────────────────────────
# CARGAR EMPRESAS.JSON
# ─────────────────────────────────────────────

def load_empresas():

    posibles_rutas = [

        "FrontEnd/Data/empresas.json",
        "../FrontEnd/Data/empresas.json",
        "Data/empresas.json",
        "empresas.json"

    ]

    for ruta in posibles_rutas:

        try:

            path = pathlib.Path(ruta)

            if path.exists():

                data = json.loads(path.read_text(encoding="utf-8"))

                print(f"✅ empresas.json cargado ({len(data)} empresas)")

                return data

        except Exception:
            continue

    print("⚠️ empresas.json no encontrado")

    return []


# ─────────────────────────────────────────────
# UNIVERSO POR SECTOR
# ─────────────────────────────────────────────

def get_universe_by_sector(sector: str):

    empresas = load_empresas()

    tickers = [

        e["ticker"]

        for e in empresas

        if e.get("sector") == sector

    ]

    return tickers


# ─────────────────────────────────────────────
# COMPS
# ─────────────────────────────────────────────

@router.post("/comps")
def generar_comps(request: CompsRequest):

    print(f"\n📨 Comps request: {request.mensaje}")

    try:

        # parámetros del deal

        if request.empresa_override and request.sector_override and request.revenue_override:

            empresa = request.empresa_override
            sector = request.sector_override
            revenue = request.revenue_override

        else:

            raise HTTPException(
                status_code=400,
                detail="Debe enviar empresa_override, sector_override y revenue_override"
            )

        tickers = get_universe_by_sector(sector)

        if not tickers:

            raise HTTPException(
                status_code=400,
                detail=f"No hay empresas cargadas para el sector {sector}"
            )

        tickers = tickers[:25]

        resultados = []

        for i, ticker in enumerate(tickers, 1):

            try:

                print(f"[{i}/{len(tickers)}] {ticker}")

                data = get_financials_ttm(ticker)

                if not data:
                    continue

                if data.get("Revenue ($mm)") is None:
                    continue

                resultados.append(data)

            except Exception:
                continue

            time.sleep(0.03)

        if not resultados:

            raise HTTPException(
                status_code=500,
                detail="No se pudieron obtener datos financieros"
            )

        rango_min = request.rango_min_pct / 100
        rango_max = request.rango_max_pct / 100

        response = build_comps_response(

            empresas=resultados,
            empresa_target=empresa,
            sector=sector,
            revenue_target=revenue,
            rango_min_pct=rango_min,
            rango_max_pct=rango_max

        )

        df = pd.DataFrame(resultados)

        DEAL_CONFIG.update({

            "empresa_target": empresa,
            "sector": sector,
            "revenue_target": revenue,
            "rango_min_pct": rango_min,
            "rango_max_pct": rango_max,
            "analista": request.analista,
            "fecha": datetime.now().strftime("%d/%m/%Y"),

        })

        try:

            archivo = generar_excel(df)

            response["archivo"] = archivo

        except Exception:

            response["archivo"] = None

        response["mensaje"] = (

            f"✅ Comps de {empresa} listos. "
            f"{response['n_empresas_filtradas']} empresas filtradas."

        )

        return response

    except HTTPException:
        raise

    except Exception as e:

        print("ERROR /comps:", e)

        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# EXCEL DOWNLOAD
# ─────────────────────────────────────────────

@router.post("/comps/excel")
def descargar_excel(request: CompsRequest):

    empresa = request.empresa_override
    sector = request.sector_override
    revenue = request.revenue_override

    tickers = get_universe_by_sector(sector)[:25]

    resultados = []

    for ticker in tickers:

        data = get_financials_ttm(ticker)

        if not data:
            continue

        if data.get("Revenue ($mm)") is None:
            continue

        resultados.append(data)

    if not resultados:

        raise HTTPException(
            status_code=500,
            detail="No se pudieron obtener datos"
        )

    df = pd.DataFrame(resultados)

    DEAL_CONFIG.update({

        "empresa_target": empresa,
        "sector": sector,
        "revenue_target": revenue,
        "rango_min_pct": request.rango_min_pct / 100,
        "rango_max_pct": request.rango_max_pct / 100,
        "analista": request.analista,
        "fecha": datetime.now().strftime("%d/%m/%Y"),

    })

    fecha_str = datetime.now().strftime("%Y%m%d")

    fname = f"Comps_{empresa.replace(' ','_')}_{fecha_str}.xlsx"

    buffer = io.BytesIO()

    _generar_excel_buffer(df, buffer)

    buffer.seek(0)

    return StreamingResponse(

        buffer,

        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",

        headers={

            "Content-Disposition": f'attachment; filename="{fname}"'

        }

    )
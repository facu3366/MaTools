from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

import pathlib
import json
import os
import sys
import pandas as pd
import io
import traceback
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from Backend.financial_engine import (
    get_financials_ttm,
    build_comps_response
)

from Backend.comps_automatico import (
    _generar_excel_buffer,
    DEAL_CONFIG
)

router = APIRouter()


# ─────────────────────────────────────────────
# MODELO REQUEST
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
# LOAD EMPRESAS.JSON
# ─────────────────────────────────────────────

def load_empresas():

    base = pathlib.Path(__file__).resolve().parents[2]

    posibles_rutas = [
        base / "FrontEnd" / "Data" / "empresas.json",
        base / "Data" / "empresas.json",
        base / "empresas.json"
    ]

    for path in posibles_rutas:
        try:
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

    return [
        e["ticker"]
        for e in empresas
        if e.get("sector", "").lower() == sector.lower()
    ]


# ─────────────────────────────────────────────
# COMPS API
# ─────────────────────────────────────────────

@router.post("/comps")
def generar_comps(request: CompsRequest):

    try:

        empresa = request.empresa_override
        sector = request.sector_override
        revenue = request.revenue_override

        tickers = get_universe_by_sector(sector)[:50]

        empresas = []

        for ticker in tickers:

            data = get_financials_ttm(ticker)

            if not data:
                continue

            empresas.append(data)

        if not empresas:
            raise HTTPException(
                status_code=500,
                detail="No se pudieron obtener empresas"
            )

        result = build_comps_response(
            empresas,
            empresa,
            sector,
            revenue,
            request.rango_min_pct / 100,
            request.rango_max_pct / 100
        )

        return result

    except Exception as e:

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ─────────────────────────────────────────────
# EXCEL DOWNLOAD
# ─────────────────────────────────────────────

@router.post("/comps/excel")
def descargar_excel(request: CompsRequest):

    try:

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

    except Exception as e:

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
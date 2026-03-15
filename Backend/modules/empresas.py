from fastapi import APIRouter, HTTPException
import pathlib
import json

router = APIRouter()

# ─────────────────────────────────────────────
# AUTOCOMPLETE — catálogo de empresas
# ─────────────────────────────────────────────

@router.get("/api/empresas")
def get_empresas():
    """
    Devuelve el catálogo de empresas para autocomplete del frontend.
    Lee el archivo FrontEnd/Data/empresas.json.
    """

    posibles_rutas = [
        "FrontEnd/Data/empresas.json",
        "../FrontEnd/Data/empresas.json",
        "Data/empresas.json",
        "empresas.json",
    ]

    for ruta in posibles_rutas:

        path = pathlib.Path(ruta)

        if path.exists():

            try:

                data = json.loads(path.read_text(encoding="utf-8"))

                print(f"✅ empresas.json cargado desde: {ruta} ({len(data)} empresas)")

                return data

            except Exception as e:

                raise HTTPException(
                    status_code=500,
                    detail=f"Error leyendo empresas.json: {str(e)}"
                )

    raise HTTPException(
        status_code=500,
        detail="No se encontró el archivo empresas.json"
    )
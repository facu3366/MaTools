from fastapi import APIRouter
from Backend.scrapers.bcra_scraper import get_bcra_bancos
from Backend.db import get_bcra_data, save_bcra_data

router = APIRouter()


@router.get("/bcra/bancos")
def bcra_bancos():

    data = get_bcra_data()

    # Si hay data → devolver DB
    if data:
        return {
            "source": "db",
            "bancos": data
        }

    # Si no hay → scrapea + guarda
    result = get_bcra_bancos()

    if "error" not in result:
        save_bcra_data(result)

    return result

@router.post("/bcra/refresh")
def refresh_bcra():

    result = get_bcra_bancos()

    if "error" in result:
        return result

    save_bcra_data(result)

    return {
        "status": "ok",
        "msg": "Datos actualizados"
    }
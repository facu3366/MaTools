"""
🏦 BCRA SCRAPER
Scraper de rankings del Banco Central de la República Argentina.

Trae automáticamente:
- Activos por banco
- Depósitos por banco  
- Patrimonio neto por banco
- Préstamos por banco

Y los consolida en una tabla única con % sobre el total.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

URLS = {
    "Activos":          "https://www.bcra.gob.ar/activos/",
    "Depositos":        "https://www.bcra.gob.ar/depositos/",
    "Patrimonio Neto":  "https://www.bcra.gob.ar/patrimonio-neto/",
    "Prestamos":        "https://www.bcra.gob.ar/prestamos/",
}

# ─────────────────────────────────────────────
# SCRAPER
# ─────────────────────────────────────────────

def limpiar_numero(texto: str) -> float | None:
    """Convierte '70.940.000.000,00' → 70940000000.0"""
    try:
        texto = texto.strip()
        # Formato argentino: puntos como miles, coma como decimal
        texto = texto.replace(".", "").replace(",", ".")
        return float(texto)
    except:
        return None


def scrape_ranking(nombre: str, url: str) -> pd.DataFrame | None:
    """Scrapea una tabla de ranking del BCRA."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table")

        if not table:
            print(f"  ⚠️  No se encontró tabla en {url}")
            return None

        # Extraer fecha de actualización
        fecha_texto = soup.find(string=lambda t: t and "actualizada" in t.lower())
        fecha = fecha_texto.strip() if fecha_texto else "N/A"

        rows = []
        for tr in table.find_all("tr")[1:]:  # skip header
            tds = tr.find_all("td")
            if len(tds) >= 3:
                orden = tds[0].get_text(strip=True)
                banco = tds[1].get_text(strip=True)
                importe_raw = tds[2].get_text(strip=True)
                importe = limpiar_numero(importe_raw)

                if banco and importe:
                    rows.append({
                        "Orden":  orden,
                        "Banco":  banco,
                        nombre:   importe,
                    })

        if not rows:
            return None

        df = pd.DataFrame(rows)
        total = df[nombre].sum()
        df[f"{nombre} %"] = (df[nombre] / total * 100).round(2)

        print(f"  ✅ {nombre}: {len(df)} bancos | Total: {total/1e9:.1f}B ARS | {fecha}")
        return df

    except Exception as e:
        print(f"  ❌ Error en {nombre}: {str(e)}")
        return None


def get_bcra_bancos(top_n: int = None) -> dict:
    """
    Trae todos los rankings del BCRA y los consolida.
    
    Args:
        top_n: si se especifica, devuelve solo los top N bancos por activos
    
    Returns:
        dict con tabla consolidada y estadísticas
    """
    print("\n🏦 Scrapeando BCRA...")
    
    dfs = {}
    for nombre, url in URLS.items():
        df = scrape_ranking(nombre, url)
        if df is not None:
            dfs[nombre] = df
        time.sleep(0.5)  # respetar el servidor

    if not dfs:
        return {"error": "No se pudieron obtener datos del BCRA"}

    # Consolidar en una sola tabla usando Banco como key
    df_base = list(dfs.values())[0][["Orden", "Banco"]].copy()
    
    for nombre, df in dfs.items():
        df_merge = df[["Banco", nombre, f"{nombre} %"]].copy()
        df_base = df_base.merge(df_merge, on="Banco", how="outer")

    # Ordenar por activos si está disponible
    if "Activos" in df_base.columns:
        df_base = df_base.sort_values("Activos", ascending=False).reset_index(drop=True)
        df_base["Rank Activos"] = range(1, len(df_base) + 1)

    if top_n:
        df_base = df_base.head(top_n)

    # Convertir a miles de millones para legibilidad
    cols_importe = ["Activos", "Depositos", "Patrimonio Neto", "Prestamos"]
    df_display = df_base.copy()
    for col in cols_importe:
        if col in df_display.columns:
            df_display[f"{col} (B ARS)"] = (df_display[col] / 1e9).round(1)

    # Calcular ROA y ROE si tenemos los datos
    # (se agregan manualmente o desde otra fuente)
    
    return {
        "fecha_scraping": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "fuente": "Banco Central de la República Argentina — bcra.gob.ar",
        "n_bancos": len(df_base),
        "bancos": df_display.to_dict(orient="records"),
        "totales": {
            "activos_total_b_ars":        round(df_base["Activos"].sum() / 1e9, 1) if "Activos" in df_base.columns else None,
            "depositos_total_b_ars":      round(df_base["Depositos"].sum() / 1e9, 1) if "Depositos" in df_base.columns else None,
            "patrimonio_total_b_ars":     round(df_base["Patrimonio Neto"].sum() / 1e9, 1) if "Patrimonio Neto" in df_base.columns else None,
            "prestamos_total_b_ars":      round(df_base["Prestamos"].sum() / 1e9, 1) if "Prestamos" in df_base.columns else None,
        }
    }


# ─────────────────────────────────────────────
# MAIN — test local
# ─────────────────────────────────────────────

if __name__ == "__main__":
    resultado = get_bcra_bancos(top_n=20)
    
    if "error" in resultado:
        print(f"\n❌ {resultado['error']}")
    else:
        print(f"\n📊 Resultado consolidado — {resultado['fecha_scraping']}")
        print(f"   {resultado['n_bancos']} bancos encontrados")
        print(f"\n   Totales del sistema:")
        for k, v in resultado["totales"].items():
            if v:
                print(f"   {k}: {v:,.1f}B ARS")
        
        print(f"\n   Top 10 bancos por activos:")
        for b in resultado["bancos"][:10]:
            nombre = b.get("Banco", "N/A")
            activos = b.get("Activos (B ARS)", 0)
            pct = b.get("Activos %", 0)
            print(f"   {nombre:<30} {activos:>8.1f}B ARS  ({pct:.1f}%)")
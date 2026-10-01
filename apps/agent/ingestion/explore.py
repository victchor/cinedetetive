"""Exploração do Wikipedia Movie Plots. Só lê e imprime; não altera nada.

Uso (dentro de apps/agent):  uv run python ingestion/explore.py
"""

import json
import math

import pandas as pd

from cinedetetive.config import ROOT_DIR, settings

CSV = settings.data_dir / "raw" / "wiki_movie_plots_deduped.csv"
CASOS = ROOT_DIR / "apps" / "agent" / "evals" / "datasets" / "manual.jsonl"

TAMANHO_TRECHO = 800
SOBREPOSICAO = 0.15
MINIMO_SINOPSE = 300

pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 20)

df = pd.read_csv(CSV)

print("=== Forma ===")
print(df.shape)
print(df.columns.tolist())

print("\n=== Um exemplo ===")
exemplo = df.iloc[0].to_dict()
exemplo["Plot"] = exemplo["Plot"][:300] + "..."
print(exemplo)

print("\n=== Valores vazios por coluna ===")
print(df.isna().sum())

print("\n=== Tamanho das sinopses (caracteres) ===")
tamanho = df["Plot"].str.len()
print(tamanho.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).round())
print(f"Menos de {MINIMO_SINOPSE}:", (tamanho < MINIMO_SINOPSE).sum())

print("\n=== Anos ===")
print(df["Release Year"].min(), "a", df["Release Year"].max())
print(df["Release Year"].floordiv(10).mul(10).value_counts().sort_index().to_string())

print("\n=== Origens ===")
print(df["Origin/Ethnicity"].value_counts().to_string())

print("\n=== Gêneros ===")
print("Valores distintos:", df["Genre"].nunique())
print(df["Genre"].value_counts().head(20).to_string())

print("\n=== Duplicatas ===")
print("Título + ano:", df.duplicated(["Title", "Release Year"]).sum())
print("Página da Wikipedia:", df.duplicated(["Wiki Page"]).sum())

print("\n=== Marcações de referência [1] ===")
print("Sinopses com [n]:", df["Plot"].str.contains(r"\[\d+\]").sum())

print(f"\n=== Trechos estimados ({TAMANHO_TRECHO} caracteres, {SOBREPOSICAO:.0%} de sobreposição) ===")
passo = TAMANHO_TRECHO * (1 - SOBREPOSICAO)
validos = tamanho[tamanho >= MINIMO_SINOPSE]
print(int(validos.apply(lambda t: max(1, math.ceil(t / passo))).sum()), f"(só sinopses com {MINIMO_SINOPSE}+ caracteres)")

print("\n=== Os casos de teste estão no dataset? ===")
casos = [json.loads(linha) for linha in CASOS.read_text(encoding="utf-8").splitlines() if linha.strip()]
titulos = df["Title"].str.lower()
encontrados = 0
for c in casos:
    achou = df[(titulos == c["titulo"].lower()) & (df["Release Year"] == c["ano"])]
    encontrados += len(achou) > 0
    print("✅" if len(achou) else "❌", c["id"], c["titulo"], c["ano"])
print(f"{encontrados}/{len(casos)} encontrados")

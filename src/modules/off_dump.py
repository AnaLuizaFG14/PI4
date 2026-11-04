"""off_dump.py: recorte reproduzível da Open Food Facts a partir do arquivo completo (dump).

Em vez de buscar produto a produto na API (limite de 10 buscas por minuto por IP, com
falhas silenciosas), baixamos UMA vez o CSV completo da OFF, lemos em pedaços (chunks),
guardamos só o que interessa e salvamos um CSV pequeno com a data da coleta.
O arquivo grande pode ser apagado depois; o projeto passa a ler só o recorte.

Uso (na raiz do repositório, por exemplo numa célula do Colab):

    !python -m src.modules.off_dump                       # baixa, filtra e salva
    !python -m src.modules.off_dump --dump-path /content/off.csv.gz --delete-dump

Saídas:
    data/processed/products.csv        o recorte (uma linha por produto)
    data/processed/products.meta.json origem, datas, contagens de cada filtro, dados faltantes

Princípios:
* Dado ausente continua ausente (célula vazia), nunca vira 0.
* Os nomes das colunas de nutrientes seguem o padrão do projeto (nutriments_<nome>_100g),
  o mesmo que `nutrition.OFF_COLUMNS` espera.
* Se uma coluna indispensável não existir no arquivo, o script PARA e diz qual, em vez de
  gerar um recorte incompleto sem avisar.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

DUMP_URL = "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz"
USER_AGENT = "PI-IV-Fatec/1.0 (projeto academico)"

BRANDS = ["Adria", "Bauducco"]
KEYWORDS = [
    "biscoito", "bisc", "bolacha", "cookie", "cookies", "wafer", "waffer", "cracker",
    "cream cracker", "tortinha", "tortinhas", "goiabinha", "recheadinho",
    "choco biscuit", "chocobiscuit", "chico biscuit",
]
COUNTRY_TAG = "en:brazil"

# Colunas do CSV da OFF (nomes originais) ------------------------------------------------
ID_COLS = ["code", "product_name", "brands_tags", "categories_tags", "countries_tags"]
OPTIONAL_ID_COLS = ["last_modified_t"]
IMAGE_COLS = ["image_front_url", "image_url"]  # usa a primeira que existir

# CSV -> nome de saída no padrão do projeto
NUTRIENT_COLS = {
    "energy-kcal_100g": "nutriments_energy_kcal_100g",
    "energy-kj_100g": "nutriments_energy_kj_100g",
    "carbohydrates_100g": "nutriments_carbohydrates_100g",
    "sugars_100g": "nutriments_sugars_100g",
    "added-sugars_100g": "nutriments_added_sugars_100g",
    "fat_100g": "nutriments_fat_100g",
    "saturated-fat_100g": "nutriments_saturated_fat_100g",
    "fiber_100g": "nutriments_fiber_100g",
    "proteins_100g": "nutriments_proteins_100g",
    "salt_100g": "nutriments_salt_100g",
    "sodium_100g": "nutriments_sodium_100g",
    "fruits-vegetables-legumes-estimate-from-ingredients_100g": (
        "nutriments_fruits_vegetables_legumes_estimate_from_ingredients_100g"
    ),
}
# Se o CSV não tiver energy-kj_100g, `energy_100g` (que a OFF guarda em kJ) serve de reserva.
ENERGY_KJ_FALLBACK = ("energy_100g", "nutriments_energy_kj_100g")
# Nota oficial da OFF, só para validar o nosso cálculo (nunca como entrada)
REFERENCE_COLS = {"nutriscore_score": "off_nutriscore_score", "nutriscore_grade": "off_nutriscore_grade"}

# Sem estes o Nutri-Score não pode ser calculado; falta => erro
REQUIRED_NUTRIENTS = ["sugars_100g", "saturated-fat_100g", "fiber_100g", "proteins_100g"]

_CATEGORY_RE = re.compile(r"biscuit|cookie|cracker|wafer|biscoito|bolacha")
_CATEGORY_EXCLUDE = {"en:biscuits-and-cakes"}  # tag "pai": aparece também em bolos e panetones


class DumpFormatError(RuntimeError):
    """O arquivo não tem a estrutura esperada (colunas essenciais ausentes ou leitura quebrada)."""


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #
def download_dump(url: str, dest: str | Path, force: bool = False) -> dict:
    """Baixa o dump para `dest` (gravando em .part e renomeando no fim).

    Devolve {"path", "last_modified", "bytes", "downloaded"}. Se o arquivo já existe e
    `force` é falso, não baixa de novo.
    """
    dest = Path(dest)
    if dest.exists() and not force:
        return {"path": str(dest), "last_modified": None, "bytes": dest.stat().st_size, "downloaded": False}

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    with requests.get(url, stream=True, timeout=(20, 120), headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        last_modified = r.headers.get("Last-Modified")
        written, next_report = 0, 0.10
        with open(part, "wb") as f:
            for block in r.iter_content(chunk_size=1 << 20):
                f.write(block)
                written += len(block)
                if total and written / total >= next_report:
                    print(f"  baixado {written / 1e6:,.0f} MB de {total / 1e6:,.0f} MB", flush=True)
                    next_report += 0.10
    if total and written != total:
        part.unlink(missing_ok=True)
        raise DumpFormatError(f"download incompleto: {written} de {total} bytes; rode de novo")
    part.replace(dest)
    return {"path": str(dest), "last_modified": last_modified, "bytes": written, "downloaded": True}


# --------------------------------------------------------------------------- #
# Plano de colunas
# --------------------------------------------------------------------------- #
def plan_columns(available: list[str]) -> dict:
    """Decide quais colunas ler e como renomeá-las. Levanta DumpFormatError se faltar algo essencial."""
    avail = set(available)
    problems: list[str] = []

    for c in ID_COLS:
        if c not in avail:
            problems.append(c)
    image_col = next((c for c in IMAGE_COLS if c in avail), None)
    if image_col is None:
        problems.append("image_front_url (ou image_url)")

    nutrient_map = {raw: out for raw, out in NUTRIENT_COLS.items() if raw in avail}
    if "energy-kj_100g" not in avail and ENERGY_KJ_FALLBACK[0] in avail:
        nutrient_map[ENERGY_KJ_FALLBACK[0]] = ENERGY_KJ_FALLBACK[1]

    for c in REQUIRED_NUTRIENTS:
        if c not in avail:
            problems.append(c)
    if not ({"energy-kcal_100g", "energy-kj_100g", "energy_100g"} & avail):
        problems.append("energia (energy-kcal_100g, energy-kj_100g ou energy_100g)")
    if not ({"salt_100g", "sodium_100g"} & avail):
        problems.append("sal ou sódio (salt_100g, sodium_100g)")

    if problems:
        dicas = sorted(c for c in available if re.search(r"energy|salt|sodium|sugar|fiber|image", c))[:25]
        raise DumpFormatError(
            "colunas essenciais ausentes no arquivo: " + ", ".join(problems)
            + ".\nColunas parecidas que existem: " + ", ".join(dicas)
            + "\nSe a OFF renomeou algo, ajuste NUTRIENT_COLS em off_dump.py."
        )

    reference_map = {raw: out for raw, out in REFERENCE_COLS.items() if raw in avail}
    optional_missing = sorted(
        [raw for raw in NUTRIENT_COLS if raw not in avail and raw != "energy-kj_100g"]
        + [raw for raw in REFERENCE_COLS if raw not in avail]
        + ([] if "energy-kj_100g" in avail or ENERGY_KJ_FALLBACK[0] in avail else ["energy-kj_100g"])
    )
    usecols = list(ID_COLS) + [image_col] + [c for c in OPTIONAL_ID_COLS if c in avail]
    usecols += list(nutrient_map) + list(reference_map)
    return {
        "usecols": list(dict.fromkeys(usecols)),
        "image_col": image_col,
        "nutrient_map": nutrient_map,
        "reference_map": reference_map,
        "optional_missing": optional_missing,
        "has_last_modified": "last_modified_t" in avail,
    }


# --------------------------------------------------------------------------- #
# Filtros
# --------------------------------------------------------------------------- #
_LANG_PREFIX = re.compile(r"^[a-z]{2,3}:")


def _strip_prefix(tag: str) -> str:
    """'xx:bauducco' -> 'bauducco'. A OFF atual grava marcas com prefixo de idioma (xx: = neutro)."""
    return _LANG_PREFIX.sub("", tag.strip().lower())


def _tag_regex(values: list[str], lang_prefix: bool = False) -> str:
    alt = "|".join(re.escape(v.lower()) for v in values)
    prefix = r"(?:[a-z]{2,3}:)?" if lang_prefix else ""
    return rf"(?:^|,){prefix}(?:{alt})(?:,|$)"


def _has_biscuit_category(tags) -> bool:
    if not isinstance(tags, str):
        return False
    return any(_CATEGORY_RE.search(t) and t not in _CATEGORY_EXCLUDE for t in tags.lower().split(","))


def _has_keyword(name, keywords: list[str]) -> bool:
    if not isinstance(name, str):
        return False
    n = name.lower()
    return any(k in n for k in keywords)


def _first_brand(tags, brands: list[str]) -> str:
    toks = {_strip_prefix(t) for t in str(tags).split(",")}
    return next((b for b in brands if b.lower() in toks), "")


# --------------------------------------------------------------------------- #
# Montagem do recorte
# --------------------------------------------------------------------------- #
def build_snapshot(
    dump_path: str | Path,
    out_path: str | Path,
    brands: list[str] | None = None,
    keywords: list[str] | None = None,
    chunksize: int = 200_000,
    quoting: str = "none",
    source_info: dict | None = None,
) -> dict:
    """Lê o dump em pedaços, filtra e grava `out_path` (+ `.meta.json`). Devolve o meta."""
    brands = brands or BRANDS
    keywords = [k.lower() for k in (keywords or KEYWORDS)]
    dump_path, out_path = Path(dump_path), Path(out_path)
    q = csv.QUOTE_NONE if quoting == "none" else csv.QUOTE_MINIMAL
    read_opts = dict(sep="\t", dtype=str, quoting=q, on_bad_lines="skip", keep_default_na=False, na_values=[""])

    header = list(pd.read_csv(dump_path, nrows=0, sep="\t", quoting=q).columns)
    plan = plan_columns(header)

    brand_re, country_re = _tag_regex(brands, lang_prefix=True), _tag_regex([COUNTRY_TAG])
    funnel = Counter()
    near_miss: Counter = Counter()
    valid_codes = 0
    kept: list[pd.DataFrame] = []

    for chunk in pd.read_csv(dump_path, usecols=plan["usecols"], chunksize=chunksize, **read_opts):
        funnel["linhas_lidas"] += len(chunk)
        valid_codes += int(chunk["code"].fillna("").str.fullmatch(r"\d+").sum())

        br = chunk[chunk["countries_tags"].fillna("").str.lower().str.contains(country_re, regex=True)]
        funnel["brasil"] += len(br)

        # marcas quase iguais (ex.: "adria-alimentos") que o filtro exato deixa de fora
        toks = br["brands_tags"].dropna().str.lower().str.split(",").explode()
        wanted = {b.lower() for b in brands}
        stripped = toks.map(_strip_prefix)
        mask = stripped.str.contains("|".join(map(re.escape, wanted)), regex=True) & ~stripped.isin(wanted)
        for tok in toks[mask]:
            near_miss[tok] += 1

        sel = br[br["brands_tags"].fillna("").str.lower().str.contains(brand_re, regex=True)].copy()
        funnel["brasil_e_marca"] += len(sel)
        if sel.empty:
            continue
        sel["match_category"] = sel["categories_tags"].map(_has_biscuit_category)
        sel["match_keyword"] = sel["product_name"].map(lambda s: _has_keyword(s, keywords))
        sel = sel[sel["match_category"] | sel["match_keyword"]]
        funnel["brasil_marca_biscoito"] += len(sel)
        kept.append(sel)

    code_ok = valid_codes / funnel["linhas_lidas"] if funnel["linhas_lidas"] else 0.0
    if funnel["linhas_lidas"] and code_ok < 0.95:
        raise DumpFormatError(
            f"só {code_ok:.1%} das linhas têm 'code' numérico: a leitura provavelmente desalinhou "
            "as colunas. Tente --quoting default."
        )

    df = pd.concat(kept, ignore_index=True) if kept else pd.DataFrame(columns=plan["usecols"] + ["match_category", "match_keyword"])

    # mais recente primeiro; um produto por código de barras
    if plan["has_last_modified"]:
        df["_lm"] = pd.to_numeric(df["last_modified_t"], errors="coerce")
        df = df.sort_values("_lm", ascending=False, na_position="last")
    df = df.drop_duplicates(subset="code", keep="first")
    funnel["apos_remover_duplicados"] = len(df)

    out = pd.DataFrame(
        {
            "image_url": df[plan["image_col"]],
            "gtin": df["code"],
            "product": df["product_name"],
            "image_brand": df["brands_tags"].map(lambda t: _first_brand(t, brands).title()),
            "categories": df["categories_tags"],
        }
    )
    for raw, name in plan["nutrient_map"].items():
        out[name] = pd.to_numeric(df[raw], errors="coerce")
    for raw, name in plan["reference_map"].items():
        out[name] = pd.to_numeric(df[raw], errors="coerce") if raw == "nutriscore_score" else df[raw]
    for name in NUTRIENT_COLS.values():  # colunas opcionais ausentes ficam vazias, mas existem
        if name not in out:
            out[name] = pd.NA
    out["has_image"] = out["image_url"].notna()
    out["match_category"] = df["match_category"].values
    out["match_keyword"] = df["match_keyword"].values
    if plan["has_last_modified"]:
        out["last_modified"] = pd.to_datetime(df["_lm"], unit="s", errors="coerce").dt.strftime("%Y-%m-%d").values
    out = out.reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)

    meta = {
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "arquivo_origem": str(dump_path),
        "origem": source_info or {},
        "marcas": brands,
        "pais": COUNTRY_TAG,
        "coluna_de_imagem": plan["image_col"],
        "funil": dict(funnel),
        "so_categoria": int((out["match_category"] & ~out["match_keyword"]).sum()),
        "so_nome": int((~out["match_category"] & out["match_keyword"]).sum()),
        "com_imagem": int(out["has_image"].sum()),
        "colunas_opcionais_ausentes_no_arquivo": plan["optional_missing"],
        "marcas_quase_iguais_deixadas_de_fora": dict(near_miss.most_common(10)),
        "fracao_de_codigos_validos": round(code_ok, 4),
        "faltantes_por_coluna": {c: int(out[c].isna().sum()) for c in out.columns if c.startswith(("nutriments_", "off_"))},
    }
    meta.update(_completeness(out))
    out_path.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def _completeness(out: pd.DataFrame) -> dict:
    """Quantos produtos têm dados para o Nutri-Score e o que mais falta (usa nutrition.py)."""
    try:
        from .nutrition import nutriscore_2023, row_to_nutrients
    except ImportError:  # executado fora do pacote
        return {}
    scoreable, missing = 0, Counter()
    for _, row in out.iterrows():
        res = nutriscore_2023(row_to_nutrients(row))
        if res.score is not None:
            scoreable += 1
        missing.update(res.missing)
    return {"com_dados_para_nutriscore": scoreable, "campos_que_mais_faltam_para_nutriscore": dict(missing)}


# --------------------------------------------------------------------------- #
# Linha de comando
# --------------------------------------------------------------------------- #
def _print_summary(meta: dict) -> None:
    f = meta["funil"]
    print("\nResumo do recorte")
    print(f"  linhas lidas no dump ........ {f.get('linhas_lidas', 0):>10,}")
    print(f"  do Brasil ................... {f.get('brasil', 0):>10,}")
    print(f"  ... e das marcas ............ {f.get('brasil_e_marca', 0):>10,}")
    print(f"  ... e biscoito .............. {f.get('brasil_marca_biscoito', 0):>10,}")
    print(f"  sem duplicados (final) ...... {f.get('apos_remover_duplicados', 0):>10,}")
    print(f"  com imagem .................. {meta['com_imagem']:>10,}")
    if "com_dados_para_nutriscore" in meta:
        print(f"  com dados p/ Nutri-Score .... {meta['com_dados_para_nutriscore']:>10,}")
        print(f"  faltam (campo: produtos) .... {meta['campos_que_mais_faltam_para_nutriscore']}")
    if meta["marcas_quase_iguais_deixadas_de_fora"]:
        print(f"  ATENCAO marcas parecidas deixadas de fora: {meta['marcas_quase_iguais_deixadas_de_fora']}")
    if meta["colunas_opcionais_ausentes_no_arquivo"]:
        print(f"  colunas opcionais ausentes: {meta['colunas_opcionais_ausentes_no_arquivo']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gera o recorte de biscoitos a partir do dump completo da Open Food Facts.")
    p.add_argument("--dump-path", default="data/raw/en.openfoodfacts.org.products.csv.gz")
    p.add_argument("--out", default="data/processed/products.csv")
    p.add_argument("--url", default=DUMP_URL)
    p.add_argument("--no-download", action="store_true", help="usar só o arquivo que já está em --dump-path")
    p.add_argument("--force-download", action="store_true")
    p.add_argument("--brands", nargs="+", default=BRANDS)
    p.add_argument("--chunksize", type=int, default=200_000)
    p.add_argument("--quoting", choices=["none", "default"], default="none")
    p.add_argument("--delete-dump", action="store_true", help="apaga o arquivo grande no fim")
    a = p.parse_args(argv)

    info: dict = {"url": a.url}
    if not a.no_download:
        print(f"Baixando {a.url} (uma vez; pode levar alguns minutos)...")
        info.update(download_dump(a.url, a.dump_path, force=a.force_download))
    elif not Path(a.dump_path).exists():
        print(f"Arquivo não encontrado: {a.dump_path}", file=sys.stderr)
        return 1
    if not info.get("last_modified"):
        mtime = datetime.fromtimestamp(Path(a.dump_path).stat().st_mtime, timezone.utc)
        info["arquivo_modificado_em_utc"] = mtime.isoformat(timespec="seconds")

    print("Lendo em pedaços e filtrando...")
    meta = build_snapshot(a.dump_path, a.out, brands=a.brands, chunksize=a.chunksize, quoting=a.quoting, source_info=info)
    _print_summary(meta)
    print(f"\nSalvo em {a.out} e {Path(a.out).with_suffix('.meta.json')}")

    if a.delete_dump:
        Path(a.dump_path).unlink(missing_ok=True)
        print("Arquivo grande apagado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

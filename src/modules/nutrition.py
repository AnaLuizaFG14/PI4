"""nutrition.py — classificação nutricional (Anvisa + Nutri-Score 2023) para o PI-IV.

Duas normas, mesma entrada (nutrientes por 100 g):

* Anvisa (RDC 429/2020 + IN 75/2020, Anexo XV): selos "alto em" açúcares
  adicionados, gordura saturada e sódio.
* Nutri-Score, versão 2023, algoritmo de "alimentos gerais" (não vale para
  bebidas, gorduras/óleos/oleaginosas nem queijos): nota numérica + letra A-E.

Princípio central: **dado ausente NÃO é zero.** Todo campo é Optional[float];
`None` significa "não informado". Quando falta um dado obrigatório, o resultado
é `None`/"indeterminado" e a lista `missing` diz o que faltou.

Fontes (conferidas em 04/11/2026):
* Tabelas de pontos do Nutri-Score 2023: implementação de referência da Open Food
  Facts, openfoodfacts-server, lib/ProductOpener/Nutriscore.pm
  (`%points_thresholds_2023`, `compute_nutriscore_score_2023`,
  `compute_nutriscore_grade_2023`). Relatório que define o algoritmo: "Update of the
  Nutri-Score algorithm — Update report from the Scientific Committee", 2022.
* Limites da Anvisa: IN 75/2020, Anexo XV (sólidos: açúcares adicionados >= 15 g,
  gordura saturada >= 6 g, sódio >= 600 mg por 100 g; líquidos: 7,5 g / 3 g / 300 mg
  por 100 ml).
* Conversão sódio/sal: sódio = sal / 2,5 (convenção usada pela Open Food Facts).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

KCAL_TO_KJ = 4.184
EPS = 1e-9  # tolerância de ponto flutuante: 0,56 g de sódio x 2,5 = 1,4000000000000001 g de sal
SALT_PER_SODIUM = 2.5  # sal (g) = sódio (g) * 2,5

Status = Literal["sim", "nao", "indeterminado"]


# --------------------------------------------------------------------------- #
# Entrada
# --------------------------------------------------------------------------- #
@dataclass
class Nutrients:
    """Nutrientes por 100 g (ou 100 ml). Unidades: g, exceto energia.

    `sodium` em GRAMAS (unidade da Open Food Facts), não em mg.
    `None` = não informado.
    """

    energy_kj: Optional[float] = None
    energy_kcal: Optional[float] = None
    carbohydrates: Optional[float] = None
    sugars: Optional[float] = None
    added_sugars: Optional[float] = None
    fat: Optional[float] = None
    saturated_fat: Optional[float] = None
    fiber: Optional[float] = None
    proteins: Optional[float] = None
    salt: Optional[float] = None
    sodium: Optional[float] = None
    fruits_veg_legumes_pct: Optional[float] = None

    @property
    def sodium_mg(self) -> Optional[float]:
        return None if self.sodium is None else self.sodium * 1000


def complete(n: Nutrients) -> tuple[Nutrients, list[str]]:
    """Deriva campos equivalentes (kcal→kJ, sódio↔sal) sem inventar dados.

    Devolve uma cópia e as notas do que foi derivado/inconsistente.
    """
    out = Nutrients(**n.__dict__)
    notes: list[str] = []

    if out.energy_kj is None and out.energy_kcal is not None:
        out.energy_kj = out.energy_kcal * KCAL_TO_KJ
        notes.append("energia em kJ derivada de kcal (x 4,184)")

    if out.salt is None and out.sodium is not None:
        out.salt = out.sodium * SALT_PER_SODIUM
        notes.append("sal derivado do sódio (x 2,5)")
    elif out.sodium is None and out.salt is not None:
        out.sodium = out.salt / SALT_PER_SODIUM
        notes.append("sódio derivado do sal (/ 2,5)")
    elif out.salt is not None and out.sodium is not None:
        esperado = out.sodium * SALT_PER_SODIUM
        if abs(out.salt - esperado) > 0.15 * max(out.salt, esperado, 0.01):
            notes.append(
                f"sal ({out.salt:g} g) e sódio ({out.sodium:g} g) não são "
                "equivalentes; usando o sal informado"
            )
    return out, notes


# --------------------------------------------------------------------------- #
# Anvisa — rotulagem nutricional frontal
# --------------------------------------------------------------------------- #
# (açúcares adicionados g, gordura saturada g, sódio mg), >= limite => "alto em"
ANVISA_LIMITS = {"solid": (15.0, 6.0, 600.0), "liquid": (7.5, 3.0, 300.0)}


@dataclass
class FopResult:
    added_sugars: Status
    saturated_fat: Status
    sodium: Status
    sugar_basis: str
    stamps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _at_least(value: Optional[float], limit: float) -> Status:
    if value is None:
        return "indeterminado"
    return "sim" if value >= limit - EPS else "nao"


def anvisa_front_label(n: Nutrients, state: Literal["solid", "liquid"] = "solid") -> FopResult:
    """Selos "alto em" da Anvisa.

    Açúcares: usa `added_sugars` se existir. Se só houver açúcares totais, vale a
    desigualdade (adicionados <= totais): total abaixo do limite => "nao" com
    certeza; total no limite ou acima => "indeterminado" (pode ter açúcar natural).
    """
    n, notes = complete(n)
    lim_sugar, lim_sat, lim_sodium = ANVISA_LIMITS[state]

    if n.added_sugars is not None:
        sugar = _at_least(n.added_sugars, lim_sugar)
        basis = "açúcares adicionados"
    elif n.sugars is not None and n.sugars < lim_sugar:
        sugar, basis = "nao", "açúcares totais abaixo do limite (adicionados também)"
    elif n.sugars is not None:
        sugar, basis = "indeterminado", "só açúcares totais, que atingem o limite"
        notes.append("açúcares adicionados não informados; totais atingem o limite")
    else:
        sugar, basis = "indeterminado", "sem dado de açúcares"

    sat = _at_least(n.saturated_fat, lim_sat)
    sodium = _at_least(n.sodium_mg, lim_sodium)

    names = {"added_sugars": "açúcares adicionados", "saturated_fat": "gordura saturada", "sodium": "sódio"}
    stamps = [names[k] for k, v in (("added_sugars", sugar), ("saturated_fat", sat), ("sodium", sodium)) if v == "sim"]
    return FopResult(sugar, sat, sodium, basis, stamps, notes)


# --------------------------------------------------------------------------- #
# Nutri-Score 2023 — alimentos gerais
# --------------------------------------------------------------------------- #
# Pontos = quantos limiares o valor ULTRAPASSA (estritamente maior).
THRESHOLDS_2023 = {
    "energy": [335, 670, 1005, 1340, 1675, 2010, 2345, 2680, 3015, 3350],  # kJ/100 g
    "sugars": [3.4, 6.8, 10, 14, 17, 20, 24, 27, 31, 34, 37, 41, 44, 48, 51],  # g
    "saturated_fat": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],  # g
    "salt": [round(0.2 * i, 1) for i in range(1, 21)],  # 0,2 ... 4,0 g (20 pontos)
    "fruits_veg_legumes": [40, 60, 80, 80, 80],  # %
    "fiber": [3.0, 4.1, 5.2, 6.3, 7.4],  # g
    "proteins": [2.4, 4.8, 7.2, 9.6, 12, 14, 17],  # g
}
# Proteína só conta se os pontos negativos forem < 11 (alimentos gerais).
PROTEIN_NEGATIVE_CAP = 11
REQUIRED = ("energy_kj", "sugars", "saturated_fat", "salt", "fiber", "proteins")
# Limites de nota por letra (alimentos gerais): A <= 0, B <= 2, C <= 10, D <= 18, E > 18.
GRADE_LIMITS = [(0, "A"), (2, "B"), (10, "C"), (18, "D")]


def _points(value: float, thresholds: list[float]) -> int:
    return sum(1 for t in thresholds if value > t + EPS)


def nutriscore_grade(score: int) -> str:
    for limit, letter in GRADE_LIMITS:
        if score <= limit:
            return letter
    return "E"


@dataclass
class NutriScoreResult:
    score: Optional[int]
    grade: Optional[str]
    negative_points: Optional[int] = None
    positive_points: Optional[int] = None
    points: dict[str, int] = field(default_factory=dict)
    proteins_counted: Optional[bool] = None
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def nutriscore_2023(n: Nutrients) -> NutriScoreResult:
    """Nutri-Score 2023 para alimentos gerais (ex.: biscoitos).

    Campos obrigatórios: energia, açúcares, gordura saturada, sal (ou sódio), fibra
    e proteína. Se algum faltar, devolve score/grade None e lista em `missing`.
    Frutas/vegetais/leguminosas ausente => 0 % (suposição declarada nas notas;
    razoável para biscoitos, não para outras categorias).
    """
    n, notes = complete(n)
    missing = [f for f in REQUIRED if getattr(n, f) is None]
    if missing:
        return NutriScoreResult(None, None, missing=missing, notes=notes)

    fvl = n.fruits_veg_legumes_pct
    if fvl is None:
        fvl = 0.0
        notes.append("% de frutas/vegetais/leguminosas ausente: assumido 0 %")

    T = THRESHOLDS_2023
    neg = {
        "energy": _points(n.energy_kj, T["energy"]),
        "sugars": _points(n.sugars, T["sugars"]),
        "saturated_fat": _points(n.saturated_fat, T["saturated_fat"]),
        "salt": _points(n.salt, T["salt"]),
    }
    negative = sum(neg.values())
    count_proteins = negative < PROTEIN_NEGATIVE_CAP

    pos = {
        "fruits_veg_legumes": _points(fvl, T["fruits_veg_legumes"]),
        "fiber": _points(n.fiber, T["fiber"]),
        "proteins": _points(n.proteins, T["proteins"]) if count_proteins else 0,
    }
    positive = sum(pos.values())
    score = negative - positive
    return NutriScoreResult(
        score=score,
        grade=nutriscore_grade(score),
        negative_points=negative,
        positive_points=positive,
        points={**neg, **pos},
        proteins_counted=count_proteins,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# Checagens de consistência (qualidade do dado, não da norma)
# --------------------------------------------------------------------------- #
def check_consistency(n: Nutrients, energy_tolerance: float = 0.20, max_salt_g: float = 10.0) -> list[str]:
    """Sinaliza dados fisicamente improváveis (erro de unidade, valor por porção etc.)."""
    n, _ = complete(n)
    flags: list[str] = []

    # energia: só kJ informado => deriva kcal para a checagem; ambos informados => devem concordar
    if n.energy_kj is not None and n.energy_kcal is None:
        n = Nutrients(**{**n.__dict__, "energy_kcal": n.energy_kj / KCAL_TO_KJ})
    elif n.energy_kj is not None and n.energy_kcal is not None and n.energy_kcal > 0:
        if abs(n.energy_kj / KCAL_TO_KJ - n.energy_kcal) / n.energy_kcal > 0.10:
            flags.append(f"kJ ({n.energy_kj:g}) e kcal ({n.energy_kcal:g}) discordantes")

    if n.sugars is not None and n.carbohydrates is not None and n.sugars > n.carbohydrates + 0.01:
        flags.append("açúcares > carboidratos")
    if n.saturated_fat is not None and n.fat is not None and n.saturated_fat > n.fat + 0.01:
        flags.append("gordura saturada > gordura total")

    macros = [v for v in (n.carbohydrates, n.proteins, n.fat) if v is not None]
    if len(macros) == 3 and sum(macros) > 100.5:
        flags.append("carboidratos + proteínas + gorduras > 100 g")

    if None not in (n.energy_kcal, n.carbohydrates, n.proteins, n.fat):
        calc = 4 * n.carbohydrates + 4 * n.proteins + 9 * n.fat
        if calc > 0 and abs(n.energy_kcal - calc) / calc > energy_tolerance:
            flags.append(f"energia ({n.energy_kcal:g} kcal) difere da calculada pelos macros (~{calc:.0f} kcal)")

    if n.salt is not None and n.salt > max_salt_g:
        flags.append(f"sal improvável ({n.salt:g} g/100 g): possível erro de unidade")
    return flags


# --------------------------------------------------------------------------- #
# Integração com o DataFrame da Open Food Facts
# --------------------------------------------------------------------------- #
OFF_COLUMNS = {
    "energy_kcal": "nutriments_energy_kcal_100g",
    "energy_kj": "nutriments_energy_kj_100g",
    "carbohydrates": "nutriments_carbohydrates_100g",
    "sugars": "nutriments_sugars_100g",
    "added_sugars": "nutriments_added_sugars_100g",
    "fat": "nutriments_fat_100g",
    "saturated_fat": "nutriments_saturated_fat_100g",
    "fiber": "nutriments_fiber_100g",
    "proteins": "nutriments_proteins_100g",
    "salt": "nutriments_salt_100g",
    "sodium": "nutriments_sodium_100g",
    "fruits_veg_legumes_pct": "nutriments_fruits_vegetables_legumes_estimate_from_ingredients_100g",
}


def _clean(value) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if (v != v or v in (float("inf"), float("-inf")) or v < 0) else v  # NaN, inf, negativo -> None


def row_to_nutrients(row, columns: dict[str, str] = OFF_COLUMNS) -> Nutrients:
    """Converte uma linha (dict ou pandas.Series) em Nutrients. Coluna ausente => None."""
    get = row.get if hasattr(row, "get") else (lambda k: row[k])
    return Nutrients(**{field_: _clean(get(col)) for field_, col in columns.items()})


def score_dataframe(df, columns: dict[str, str] = OFF_COLUMNS):
    """Devolve uma cópia de `df` com colunas das duas normas e das checagens."""
    out = df.copy()
    rows = []
    for _, row in df.iterrows():
        n = row_to_nutrients(row, columns)
        ns, fop, flags = nutriscore_2023(n), anvisa_front_label(n), check_consistency(n)
        rows.append(
            {
                "ns_score": ns.score,
                "ns_grade": ns.grade,
                "ns_missing": ", ".join(ns.missing),
                "ns_notes": "; ".join(ns.notes),
                "anvisa_stamps": ", ".join(fop.stamps),
                "anvisa_added_sugars": fop.added_sugars,
                "anvisa_saturated_fat": fop.saturated_fat,
                "anvisa_sodium": fop.sodium,
                "quality_flags": "; ".join(flags),
            }
        )
    import pandas as pd

    return pd.concat([out.reset_index(drop=True), pd.DataFrame(rows)], axis=1)

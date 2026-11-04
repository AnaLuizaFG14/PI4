"""Testes de nutrition.py. Rodar com:  pytest -v

Os valores esperados foram calculados À MÃO a partir das tabelas de pontos (ver
docstring de nutrition.py), não gerados pelo próprio código.
"""

import pytest

from src.modules.nutrition import (
    Nutrients,
    anvisa_front_label,
    check_consistency,
    complete,
    nutriscore_2023,
    row_to_nutrients,
    score_dataframe,
)


# ---------- conversões ----------
def test_kcal_to_kj():
    n, _ = complete(Nutrients(energy_kcal=100))
    assert n.energy_kj == pytest.approx(418.4)


def test_sodium_to_salt_and_back():
    n, _ = complete(Nutrients(sodium=0.4))
    assert n.salt == pytest.approx(1.0)
    n, _ = complete(Nutrients(salt=1.0))
    assert n.sodium == pytest.approx(0.4)
    assert n.sodium_mg == pytest.approx(400)


# ---------- Nutri-Score 2023 ----------
def test_biscoito_agua_e_sal_adria():
    # 452 kcal (1891 kJ), açúcares 3,1, sat 4,4, sódio 0,526 g (sal 1,315 g), fibra 1,9, prot 11
    # energia 5 + açúcares 0 + sat 4 + sal 6 = 15 (>= 11, proteína NÃO conta); fibra 0 => 15 => D
    r = nutriscore_2023(
        Nutrients(energy_kcal=452, sugars=3.1, saturated_fat=4.4, sodium=0.526, fiber=1.9, proteins=11)
    )
    assert r.negative_points == 15
    assert r.proteins_counted is False
    assert (r.score, r.grade) == (15, "D")


def test_produto_favoravel_nota_A():
    # energia 4 + açúcares 0 + sat 1 + sal 0 = 5; fibra 8 => 5, proteína 13 => 5; 5 - 10 = -5 => A
    r = nutriscore_2023(
        Nutrients(energy_kj=1600, sugars=1, saturated_fat=1.5, salt=0.02, fiber=8, proteins=13)
    )
    assert (r.score, r.grade) == (-5, "A")


def test_limiar_e_estritamente_maior():
    base = dict(energy_kj=0, saturated_fat=0, salt=0, fiber=0, proteins=0)
    assert nutriscore_2023(Nutrients(sugars=3.4, **base)).points["sugars"] == 0
    assert nutriscore_2023(Nutrients(sugars=3.41, **base)).points["sugars"] == 1
    assert nutriscore_2023(Nutrients(sugars=0, fruits_veg_legumes_pct=40, **base)).points["fruits_veg_legumes"] == 0
    assert nutriscore_2023(Nutrients(sugars=0, fruits_veg_legumes_pct=41, **base)).points["fruits_veg_legumes"] == 1


def test_proteina_conta_com_10_pontos_negativos_e_nao_com_11():
    # energia 2100 kJ => 6; sat 1,5 => 1; açúcares 10,1 => 3; sal 0 => 0  => 10 negativos
    base = dict(energy_kj=2100, saturated_fat=1.5, salt=0, fiber=0, proteins=12.5)
    r10 = nutriscore_2023(Nutrients(sugars=10.1, **base))
    assert r10.negative_points == 10 and r10.proteins_counted is True
    assert (r10.score, r10.grade) == (5, "C")  # 10 - 5 pontos de proteína
    # açúcares 14,1 => 4 pontos => 11 negativos: proteína deixa de contar
    r11 = nutriscore_2023(Nutrients(sugars=14.1, **base))
    assert r11.negative_points == 11 and r11.proteins_counted is False
    assert (r11.score, r11.grade) == (11, "D")


@pytest.mark.parametrize("score,letter", [(0, "A"), (1, "B"), (2, "B"), (3, "C"), (10, "C"), (11, "D"), (18, "D"), (19, "E")])
def test_letras(score, letter):
    from src.modules.nutrition import nutriscore_grade

    assert nutriscore_grade(score) == letter


def test_dado_ausente_nao_vira_zero():
    # sem gordura saturada: NÃO deve calcular como se fosse 0
    r = nutriscore_2023(Nutrients(energy_kcal=480, sugars=30, salt=0.3, fiber=1, proteins=5))
    assert r.score is None and r.grade is None
    assert r.missing == ["saturated_fat"]


# ---------- Anvisa ----------
@pytest.mark.parametrize(
    "added,expected", [(14.9, "nao"), (15.0, "sim"), (None, "indeterminado")]
)
def test_anvisa_acucares_adicionados(added, expected):
    # com total = 20 e adicionados desconhecidos, não dá para afirmar
    r = anvisa_front_label(Nutrients(added_sugars=added, sugars=20))
    assert r.added_sugars == expected


def test_anvisa_total_abaixo_do_limite_garante_nao():
    assert anvisa_front_label(Nutrients(sugars=14)).added_sugars == "nao"


def test_anvisa_gordura_saturada_e_sodio():
    r = anvisa_front_label(Nutrients(saturated_fat=6, sodium=0.600, sugars=0))
    assert r.saturated_fat == "sim" and r.sodium == "sim"
    r = anvisa_front_label(Nutrients(saturated_fat=5.99, sodium=0.599, sugars=0))
    assert r.saturated_fat == "nao" and r.sodium == "nao"


def test_anvisa_sodio_derivado_do_sal():
    # sal 1,5 g => sódio 0,6 g = 600 mg => selo
    assert anvisa_front_label(Nutrients(salt=1.5)).sodium == "sim"


def test_anvisa_liquido_usa_limites_proprios():
    assert anvisa_front_label(Nutrients(added_sugars=7.5), state="liquid").added_sugars == "sim"
    assert anvisa_front_label(Nutrients(added_sugars=7.5), state="solid").added_sugars == "nao"


def test_anvisa_lista_selos():
    r = anvisa_front_label(Nutrients(added_sugars=30, saturated_fat=9, sodium=0.1))
    assert r.stamps == ["açúcares adicionados", "gordura saturada"]


# ---------- consistência ----------
def test_consistencia_detecta_energia_por_porcao():
    # caso real do dataset: 142 kcal com 68 g carbo, 6,2 g prot, 20 g gordura (~477 kcal pelos macros)
    flags = check_consistency(Nutrients(energy_kcal=142, carbohydrates=68, proteins=6.2, fat=20))
    assert any("energia" in f for f in flags)


def test_consistencia_aceita_dado_coerente():
    flags = check_consistency(
        Nutrients(energy_kcal=452, carbohydrates=70, sugars=3.1, proteins=11, fat=14, saturated_fat=4.4, sodium=0.526)
    )
    assert flags == []


def test_consistencia_sodio_impossivel():
    assert any("sal improvável" in f for f in check_consistency(Nutrients(sodium=17.3)))


def test_consistencia_so_kj_tambem_e_checado():
    # 142 kcal = 594 kJ, mas os macros dão ~477 kcal
    assert any("energia" in f for f in check_consistency(Nutrients(energy_kj=594, carbohydrates=68, proteins=6.2, fat=20)))


def test_consistencia_kj_e_kcal_discordantes():
    assert any("discordantes" in f for f in check_consistency(Nutrients(energy_kj=2000, energy_kcal=142)))


# ---------- ponto flutuante nos limiares ----------
@pytest.mark.parametrize("sodium_g,salt_points", [(0.08, 0), (0.56, 6), (1.12, 13), (1.36, 16)])
def test_sodio_exatamente_no_limiar_nao_ganha_ponto_extra(sodium_g, salt_points):
    # 0,56 g x 2,5 = 1,4000000000000001 em float; sal 1,4 g NÃO ultrapassa o limiar 1,4 (6 pontos)
    r = nutriscore_2023(Nutrients(energy_kj=0, sugars=0, saturated_fat=0, fiber=0, proteins=0, sodium=sodium_g))
    assert r.points["salt"] == salt_points


def test_valores_invalidos_viram_nao_informado():
    n = row_to_nutrients({"nutriments_sugars_100g": -3, "nutriments_fat_100g": float("inf"), "nutriments_fiber_100g": 2})
    assert n.sugars is None and n.fat is None and n.fiber == 2


# ---------- DataFrame ----------
def test_row_to_nutrients_trata_nan_e_coluna_ausente():
    nan = float("nan")
    n = row_to_nutrients({"nutriments_sugars_100g": nan, "nutriments_fat_100g": 3.0})
    assert n.sugars is None and n.fat == 3.0 and n.salt is None


def test_score_dataframe():
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame(
        [
            {
                "product": "ok",
                "nutriments_energy_kcal_100g": 452,
                "nutriments_sugars_100g": 3.1,
                "nutriments_saturated_fat_100g": 4.4,
                "nutriments_sodium_100g": 0.526,
                "nutriments_fiber_100g": 1.9,
                "nutriments_proteins_100g": 11,
            },
            {"product": "sem dados", "nutriments_energy_kcal_100g": float("nan")},
        ]
    )
    out = score_dataframe(df)
    assert out.loc[0, "ns_grade"] == "D"
    assert out.loc[1, "ns_grade"] is None or out.loc[1, "ns_grade"] != out.loc[1, "ns_grade"]
    assert "energy_kj" in out.loc[1, "ns_missing"]

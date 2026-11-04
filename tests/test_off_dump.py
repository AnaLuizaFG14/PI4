"""Testes de off_dump.py com um dump de mentira, no mesmo formato do CSV da OFF
(tabulação, uma linha de cabeçalho, muitas colunas que não usamos). Rodar com: pytest -v
"""

import csv
import gzip
import json

import pandas as pd
import pytest

from src.modules.off_dump import DumpFormatError, build_snapshot, plan_columns

BASE_HEADER = [
    "code", "url", "product_name", "brands_tags", "categories_tags", "countries_tags",
    "last_modified_t", "image_front_url", "energy-kcal_100g", "energy-kj_100g",
    "carbohydrates_100g", "sugars_100g", "added-sugars_100g", "fat_100g", "saturated-fat_100g",
    "fiber_100g", "proteins_100g", "salt_100g", "sodium_100g", "nutriscore_score", "nutriscore_grade",
    "coluna_que_nao_usamos",
]


def row(**kw):
    base = dict.fromkeys(BASE_HEADER, "")
    base["countries_tags"] = "en:brazil"
    base["coluna_que_nao_usamos"] = "lixo"
    base.update(kw)
    return base


def write_dump(path, rows, header=None, extra_lines=()):
    header = header or BASE_HEADER
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
        for line in extra_lines:
            f.write(line + "\n")


FULL = dict(
    **{"energy-kcal_100g": "452", "energy-kj_100g": "1891", "carbohydrates_100g": "70", "sugars_100g": "3.1",
       "fat_100g": "14", "saturated-fat_100g": "4.4", "fiber_100g": "1.9", "proteins_100g": "11",
       "sodium_100g": "0.526", "salt_100g": "1.315"}
)

ROWS = [
    # 0: Adria, biscoito, completo, versão antiga
    row(code="7896000000011", product_name="Biscoito Água e Sal", brands_tags="adria,m-dias-branco",
        categories_tags="en:snacks,en:biscuits", last_modified_t="1700000000",
        image_front_url="http://img/1.jpg", **{**FULL, "sugars_100g": "9.9"}),
    # 1: mesmo código, mais novo: deve vencer na deduplicação
    row(code="7896000000011", product_name="Biscoito Água e Sal", brands_tags="adria",
        categories_tags="en:biscuits", last_modified_t="1750000000", image_front_url="http://img/1b.jpg", **FULL),
    # 2: Bauducco, wafer só por categoria (nome sem palavra-chave), sem sal e sem fibra
    row(code="7891000000022", product_name="Chocolate recheado", brands_tags="bauducco",
        categories_tags="en:wafers", last_modified_t="1740000000", image_front_url="http://img/2.jpg",
        **{"energy-kcal_100g": "500", "sugars_100g": "30", "saturated-fat_100g": "9", "proteins_100g": "5"}),
    # 3: Adria mas na Argentina
    row(code="7790000000033", product_name="Biscoito X", brands_tags="adria", categories_tags="en:biscuits",
        countries_tags="en:argentina", image_front_url="http://img/3.jpg", **FULL),
    # 4: outra marca
    row(code="7891000000044", product_name="Biscoito Y", brands_tags="nestle", categories_tags="en:biscuits",
        image_front_url="http://img/4.jpg", **FULL),
    # 5: Bauducco panetone: categoria-pai de bolos não conta, nome sem palavra-chave
    row(code="7891000000055", product_name="Panettone", brands_tags="bauducco",
        categories_tags="en:panettone,en:biscuits-and-cakes", image_front_url="http://img/5.jpg", **FULL),
    # 6: marca quase igual
    row(code="7891000000066", product_name="Biscoito Z", brands_tags="adria-alimentos",
        categories_tags="en:biscuits", image_front_url="http://img/6.jpg", **FULL),
    # 7: sem imagem: continua no recorte, marcada has_image False. Sódio ausente, sal presente
    row(code="7891000000077", product_name="Bolacha Maria", brands_tags="adria", categories_tags="en:biscuits",
        last_modified_t="1730000000", **{k: v for k, v in FULL.items() if k != "sodium_100g"}),
    # 8: marca com prefixo de idioma, como no arquivo real de hoje ("xx:bauducco")
    row(code="7891000000088", product_name="Cream Cracker", brands_tags="xx:bauducco,xx:casa-bauducco",
        categories_tags="en:crackers", last_modified_t="1745000000", image_front_url="http://img/8.jpg", **FULL),
]


@pytest.fixture
def dump(tmp_path):
    p = tmp_path / "dump.csv.gz"
    # linhas de outros países diluem a linha quebrada, como no arquivo real (milhões de linhas)
    filler = [row(code=f"30000{i:05d}", product_name="Produto", countries_tags="en:france") for i in range(60)]
    write_dump(p, ROWS + filler, extra_lines=["linha\tquebrada\tcom\tcampos\tdemais\t" + "x\t" * 60])
    return p


def run(dump, tmp_path, **kw):
    out = tmp_path / "out" / "products.csv"
    meta = build_snapshot(dump, out, **kw)
    return pd.read_csv(out, dtype={"gtin": str}), meta, out


def test_filtra_pais_marca_e_biscoito(dump, tmp_path):
    df, meta, _ = run(dump, tmp_path)
    assert set(df["gtin"]) == {"7896000000011", "7891000000022", "7891000000077", "7891000000088"}
    f = meta["funil"]
    assert f["brasil"] == 8  # tudo menos a linha da Argentina
    assert f["brasil_e_marca"] == 6  # 0, 1, 2, 5, 7, 8
    assert f["brasil_marca_biscoito"] == 5  # o panetone cai
    assert f["apos_remover_duplicados"] == 4


def test_duplicado_fica_com_a_versao_mais_nova(dump, tmp_path):
    df, _, _ = run(dump, tmp_path)
    r = df[df["gtin"] == "7896000000011"].iloc[0]
    assert r["nutriments_sugars_100g"] == pytest.approx(3.1)
    assert r["image_url"].endswith("1b.jpg")
    assert r["last_modified"] == "2025-06-15"


def test_ausente_continua_ausente_e_nao_vira_zero(dump, tmp_path):
    df, _, _ = run(dump, tmp_path)
    r = df[df["gtin"] == "7891000000022"].iloc[0]
    assert pd.isna(r["nutriments_salt_100g"]) and pd.isna(r["nutriments_fiber_100g"])
    assert r["nutriments_saturated_fat_100g"] == 9
    r7 = df[df["gtin"] == "7891000000077"].iloc[0]
    assert pd.isna(r7["nutriments_sodium_100g"]) and r7["nutriments_salt_100g"] == pytest.approx(1.315)


def test_marcas_flags_e_imagem(dump, tmp_path):
    df, meta, _ = run(dump, tmp_path)
    assert set(df["image_brand"]) == {"Adria", "Bauducco"}
    r = df.set_index("gtin")
    assert r.loc["7891000000022", "match_category"] and not r.loc["7891000000022", "match_keyword"]
    assert r.loc["7896000000011", "match_keyword"]
    assert not r.loc["7891000000077", "has_image"]
    assert meta["com_imagem"] == 3


def test_relatorio_mostra_marca_parecida_deixada_de_fora(dump, tmp_path):
    _, meta, out = run(dump, tmp_path)
    assert meta["marcas_quase_iguais_deixadas_de_fora"] == {"adria-alimentos": 1, "xx:casa-bauducco": 1}
    assert json.loads(out.with_suffix(".meta.json").read_text(encoding="utf-8"))["pais"] == "en:brazil"


def test_completude_para_nutriscore(dump, tmp_path):
    _, meta, _ = run(dump, tmp_path)
    assert meta["com_dados_para_nutriscore"] == 3  # o 7891000000022 não tem fibra nem sal
    assert meta["campos_que_mais_faltam_para_nutriscore"]["fiber"] == 1


def test_colunas_no_padrao_do_projeto(dump, tmp_path):
    from src.modules.nutrition import OFF_COLUMNS

    df, _, _ = run(dump, tmp_path)
    assert set(OFF_COLUMNS.values()) <= set(df.columns)


def test_coluna_essencial_ausente_para_com_mensagem_clara(tmp_path):
    header = [c for c in BASE_HEADER if c != "saturated-fat_100g"]
    p = tmp_path / "d.csv.gz"
    write_dump(p, ROWS, header=header)
    with pytest.raises(DumpFormatError, match="saturated-fat_100g"):
        build_snapshot(p, tmp_path / "o.csv")


def test_energia_em_kj_reserva_quando_falta_energy_kj():
    header = [c for c in BASE_HEADER if c != "energy-kj_100g"] + ["energy_100g"]
    plan = plan_columns(header)
    assert plan["nutrient_map"]["energy_100g"] == "nutriments_energy_kj_100g"


def test_leitura_desalinhada_e_detectada(tmp_path):
    bad = [row(code="abc" + str(i), product_name="x", brands_tags="adria", categories_tags="en:biscuits") for i in range(20)]
    p = tmp_path / "d.csv.gz"
    write_dump(p, bad)
    with pytest.raises(DumpFormatError, match="numérico"):
        build_snapshot(p, tmp_path / "o.csv")


def test_dump_sem_nenhum_produto_gera_recorte_vazio(tmp_path):
    p = tmp_path / "d.csv.gz"
    write_dump(p, [ROWS[3], ROWS[4]])
    out = tmp_path / "o.csv"
    meta = build_snapshot(p, out)
    assert meta["funil"]["apos_remover_duplicados"] == 0
    assert len(pd.read_csv(out)) == 0

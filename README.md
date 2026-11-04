# Projeto Integrador IV: identificação e classificação de produtos

Identifica um biscoito (Adria e Bauducco) e classifica o perfil nutricional pelas normas da Anvisa e pelo Nutri-Score 2023, com dados da Open Food Facts.

Para o contexto completo do projeto, decisões e pendências, leia o [CONTEXTO.md](CONTEXTO.md).

## Como rodar

```
pip install pandas requests pytest
python -m pytest -q
```

## Refazer o recorte de dados

O recorte já está em `data/processed/products.csv` (com `products.meta.json` ao lado). Para gerar de novo, a partir da raiz do repo (baixa ~1,5 GB):

```
python -m src.modules.off_dump
```

Opções: `--no-download` reaproveita o arquivo já baixado; `--delete-dump` apaga o arquivo grande no fim.

## Estrutura

- `src/modules/nutrition.py`: Anvisa, Nutri-Score 2023 e checagens de consistência.
- `src/modules/off_dump.py`: coleta pelo arquivo completo da Open Food Facts.
- `src/modules/api_client.py`, `data_processing.py`, `image_downloader.py`, `app.py`: coleta pela API (versão original, plano B).
- `tests/`: testes de `nutrition.py` e `off_dump.py`.
- `notebooks/colab/`: histórico do que foi rodado no Colab.

# Projeto Integrador IV: identificação e classificação de produtos

Identifica um biscoito (Adria e Bauducco) e classifica o perfil nutricional pelas normas da Anvisa e pelo Nutri-Score 2023, com dados da Open Food Facts.

Para o contexto completo do projeto, decisões e pendências, leia o [CONTEXTO.md](CONTEXTO.md).

## Como rodar

Na raiz do projeto, com o ambiente virtual ativo:

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

Na interface:

1. Envie uma ou duas fotos de embalagens (JPG, PNG ou WEBP, até 10 MB por arquivo).
2. Clique em **Encontrar produtos similares**.
3. Confira os três resultados de cada foto, com imagem do catálogo, produto, marca, GTIN e similaridade.

As fotos são comparadas separadamente. Os uploads são processados em memória e não são gravados no catálogo. A consulta reutiliza `data/embeddings.pt` e o modelo em memória; não coleta produtos nem baixa imagens do catálogo.

A base deve ser preparada antes de usar a interface. Pelo Python, execute o fluxo existente com `rebuild=True` para criar ou atualizar os vetores a partir das imagens locais. Use `download_images=True` somente quando quiser solicitar o download das imagens ausentes.

O valor de similaridade representa proximidade visual, não uma probabilidade de acerto. O DINOv2 utiliza os pesos pré-treinados; a primeira carga pode precisar de internet se os pesos ainda não estiverem no cache local.

## Testes

```bash
python -m pip install -r requirements-dev.txt
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
- `streamlit_app.py`: entrada da interface Streamlit.
- `src/streamlit_ui.py`: upload, prévias e apresentação dos resultados.
- `src/pipeline.py`: coordenação da preparação dos dados e da predição.
- `src/modules/image_encoder.py`: carregamento do DINOv2 e extração dos vetores.
- `src/modules/product_classifier.py`: criação/carregamento da base e consultas por imagem.
- `src/modules/upload_images.py`: validação das fotos enviadas e preparo das prévias.
- `src/modules/api_client.py`, `data_processing.py`, `image_downloader.py`: coleta pela API e download opcional das imagens.
- `app.py`: execução simples do fluxo pelo Python.
- `tests/`: testes da coleta, nutrição, consultas por imagem e interface.
- `notebooks/colab/`: histórico do que foi rodado no Colab.

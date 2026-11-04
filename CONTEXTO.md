# CONTEXTO do PI-IV

Leia este arquivo primeiro. Ele substitui as conversas anteriores. Atualizado em 04/11/2026.

## Objetivo e entrega

Identificar um biscoito por foto e mostrar a classificação nutricional dele (selos da Anvisa e Nutri-Score 2023), comparando as duas normas. Dados: Open Food Facts (OFF), produtos do Brasil das marcas Adria e Bauducco.

Entrega final: 11/11/2026, 23:59 (Teams, vários envios permitidos).
- App em Streamlit ou Gradio com o pipeline completo, do dado bruto até o resultado na tela, e o "modelo salvo" carregado.
- Hospedagem se possível (Streamlit Community Cloud ou Hugging Face Spaces), senão execução local documentada.
- Vídeo de demonstração de 2 a 5 min.
- Fechamento: lições aprendidas, divisão de tarefas, checklist de coerência entre relatório, código e slides (mesmos números).

Equipe: Matheus cuida da identificação por imagem; Vi e Pedro, da tabela nutricional. Repo no GitHub: AnaLuizaFG14/PI4.

## Decisões já tomadas

- Dado ausente nunca vira zero. Todo nutriente é `Optional[float]`; `None` significa "não informado". O `fillna(0)` do código antigo foi abandonado.
- As duas normas rodam lado a lado: Anvisa (RDC 429/2020 + IN 75/2020, Anexo XV) e Nutri-Score versão 2023 para alimentos gerais. Uma não é rótulo da outra, as duas são comparação.
- Nutri-Score validado contra a nota da própria OFF: nos 24 produtos em que as duas notas existem, nota e letra são idênticas (24 de 24).
- Coleta pelo arquivo completo da OFF (CSV, ~1,5 GB), lido em pedaços e filtrado; só o recorte vai para o Git. Motivo: a API tem limite de 10 buscas por minuto e o cliente antigo descartava páginas sem avisar. O Matheus aprovou a mudança.
- Conversão sal e sódio: sódio (g) = sal (g) / 2,5. A OFF guarda sódio em g/100 g; a Anvisa usa mg.
- Tratamento de qualidade de dado (decidido, ainda não implementado): flag por campo, não por linha. Só perde a nota quem tem o campo problemático dentro da conta. Manter os 33 produtos com nota e reportar o funil no relatório.

## Dados (data/processed/products.csv, coletado em 04/11/2026)

Funil: 4.893.434 linhas lidas, 37.878 do Brasil, 278 das duas marcas, 115 biscoitos (87 Bauducco, 28 Adria), 115 sem duplicados, 105 com imagem.

| Etapa | Produtos |
| --- | --- |
| Com algum dado nutricional | 102 |
| Com Nutri-Score nosso | 33 |
| Com nota da OFF | 27 |
| Gordura saturada determinada (Anvisa) | 51 |
| Sódio determinado (Anvisa) | 49 |

Nos 33 com nota: 27 em E, 4 em D, 2 em C. Selo "alto em gordura saturada": 25; "alto em sódio": 0. O Nutri-Score quase não separa biscoitos, então a nota numérica vale mais que a letra.

O que mais falta para o Nutri-Score: açúcares (74 produtos sem), fibra (67), sal (66), gordura saturada (64), proteína (14), energia (13). A coluna de frutas e vegetais não existe no arquivo da OFF, então vale 0 % para todos (registrado em `ns_notes`).

## Problemas conhecidos nos dados da OFF

- 35 produtos sinalizados em `quality_flags`; só 1 deles tem nota (Plugados Chocolate Suíço, cujo erro está em um campo que não entra na conta).
- Em 26 deles a gordura é 0 g com energia de 450 a 540 kcal: o 0 parece "não sei".
- 46 produtos com kcal de duas casas decimais (ex.: 476,67), o que sugere conta de porção para 100 g. Origem não confirmada.
- "Wafer Recheio Limão": 53 kcal com macros que dão ~535 kcal.
- "Água e Sal Levíssimo": sódio de 17,3 g/100 g, impossível. "Multigraos" tem 0,88 g de sódio, o que dá selo de sódio alto pelos dados; confira na embalagem.
- Fibra ausente: nossa conta devolve "sem nota" (3 produtos). Com fibra = 0 as três notas batem com as da OFF (15, 24, 19), então a OFF trata fibra ausente como 0.

## Não confirmado (não afirmar no relatório sem checar)

- Que a OFF não calcula nota para 8 dos 9 produtos que só nós pontuamos por falta de categoria cadastrada. Foi inferido dos dados, não da documentação.
- Origem dos valores com cara de porção.
- Tabelas de pontos de energia e gordura saturada foram conferidas só na implementação da OFF; açúcares, fibra, proteína e sal também no relatório do Comitê Científico (2022).

## Estado atual

Pronto e testado (46 testes, ~1 s):
- `src/modules/nutrition.py`: Anvisa, Nutri-Score 2023, checagens de consistência, `score_dataframe`.
- `src/modules/off_dump.py`: baixa o dump, filtra, deduplica pela versão mais nova, gera CSV e `.meta.json`. Marcas vêm com prefixo de idioma (`xx:bauducco`), tratado em `_strip_prefix`.
- Código do Matheus (`app.py`, `api_client.py`, `data_processing.py`, `image_downloader.py`) continua intacto como plano B. O `fillna(0)` dele não deve voltar.

Pendente, em ordem:
1. Flags por campo em `nutrition.py`, com testes; regra "gordura = 0 com energia > 0" como erro; opção "como a OFF" para fibra ausente.
2. Tabela final de comparação (nota nossa, nota da OFF, selos Anvisa, flags) para o relatório.
3. `streamlit_app.py` (o `app.py` atual é script de coleta). Começar com seleção manual do produto; ligar a busca por foto depois.
4. Código de imagem do Matheus no repo como módulo. Hoje está só no `PI-IV.ipynb`, células 62 a 67 (DINOv2-small, embedding CLS normalizado, `embeddings.pt` com metadata, similaridade de cosseno, top 3). É busca por semelhança, não classificador treinado; o relatório precisa dizer isso.
5. Testar cedo a hospedagem (o peso é o `torch`). Hugging Face Spaces é o plano B.
6. README completo, lições aprendidas, checklist de coerência, vídeo.

Pendente para decidir com o grupo: completar à mão os campos faltantes de 10 a 20 produtos olhando a embalagem (serve também de conferência manual); incluir ou não "Adria Plus Life".

## Convenções

- Estrutura: `src/modules/` (código), `tests/`, `data/processed/` (recorte versionado), `data/raw/` e `data/images/` fora do Git, `notebooks/colab/` (histórico do que foi rodado no Colab).
- Testes: `pytest -q` na raiz.
- Refazer o recorte no Colab: `!python -m src.modules.off_dump` (`--no-download` reaproveita o arquivo baixado, `--delete-dump` apaga o grande no fim).
- Entregas de arquivos: mandar só o que mudou (alterados e novos), porque o Vi cola por cima do projeto.
- Material antigo (notebooks de EDA, relatórios, PDFs da pasta "PI-4 completa") não está no repo; se for subido, criar a pasta `legado/` sem apagar nada do Matheus.

## Ao começar uma sessão nova

Mande só o repo (zip) e a tarefa em uma frase. Ao fechar a sessão, peça a atualização deste arquivo.

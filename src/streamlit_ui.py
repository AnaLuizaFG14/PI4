"""Interface para consultar o catálogo com uma ou duas fotos de produtos."""

from hashlib import sha256
import logging
from pathlib import Path
from threading import Lock

import streamlit as st
from PIL import Image

from src.modules.upload_images import MAX_IMAGES, MAX_UPLOAD_MB, make_preview, prepare_uploads
from src.pipeline import DATABASE_PATH, IMAGES_PATH, PRODUCTS_PATH, load_classifier


logger = logging.getLogger(__name__)


STYLES = """
<style>
    .stApp { background: #f7f7f2; }
    .block-container { max-width: 1180px; padding-top: 2.2rem; padding-bottom: 3rem; }
    h1, h2, h3 { letter-spacing: -0.035em; }
    .brand { display: flex; align-items: center; gap: .75rem; margin-bottom: 2.6rem; }
    .brand-mark { background: #173f35; color: white; padding: .55rem .75rem;
                  border-radius: 12px; font-size: .9rem; font-weight: 750; }
    .brand-title { font-size: .95rem; font-weight: 650; color: #173f35; }
    .brand-subtitle { font-size: .75rem; color: #717a72; }
    .eyebrow { color: #537565; font-size: .75rem; letter-spacing: .14em;
               font-weight: 700; text-transform: uppercase; margin-bottom: .7rem; }
    .hero-title { font-family: Georgia, serif; font-weight: 500; line-height: 1.08;
                  font-size: clamp(2.5rem, 5vw, 4rem); color: #173f35; margin-bottom: 1rem; }
    .hero-copy { max-width: 610px; color: #616b64; font-size: 1.05rem;
                 line-height: 1.7; margin-bottom: 1.4rem; }
    .pill { display: inline-block; background: #e8eee4; color: #365f4c;
             border-radius: 30px; padding: .38rem .8rem; font-size: .78rem; margin-right: .4rem; }
    .section-label { font-weight: 700; color: #213e32; font-size: 1.08rem; margin: 1.7rem 0 .5rem; }
    .empty-results { border: 1px dashed #cbd5ca; background: #eff3eb; border-radius: 16px;
                      padding: 2rem; text-align: center; margin-top: 2rem; color: #627260; }
    .empty-results strong { display: block; font-size: 1.12rem; color: #304e3c; margin-bottom: .4rem; }
    .rank { color: #3c6250; font-size: .75rem; text-transform: uppercase;
            letter-spacing: .09em; font-weight: 700; margin-bottom: .5rem; }
    .score { display: inline-block; background: #e8eee4; border-radius: 9px;
             color: #274d3b; padding: .3rem .65rem; font-size: .85rem; margin: .2rem 0 .7rem; }
    [data-testid="stVerticalBlockBorderWrapper"] > div { border-radius: 16px; }
    [data-testid="stFileUploader"] { background: #ffffff; border-radius: 14px; }
    [data-testid="stFileUploaderDropzone"] { background: #ffffff; border: 1px dashed #b7c8b7; }
    div.stButton > button[kind="primary"] { border-radius: 10px; min-height: 2.9rem; font-weight: 650; }
    .footer-note { color: #7a8279; font-size: .78rem; margin-top: 2.5rem;
                   border-top: 1px solid #e0e5dc; padding-top: 1rem; }
</style>
"""


@st.cache_resource(show_spinner=False)
def load_search_engine(database_path: str, database_version: tuple[int, int]):
    # A versão do arquivo invalida o cache se a base for atualizada.
    classifier = load_classifier(
        products_path=PRODUCTS_PATH,
        images_path=IMAGES_PATH,
        database_path=Path(database_path),
    )
    return classifier, Lock()


def show_product(result: dict, position: int) -> None:
    with st.container(border=True):
        st.markdown(f'<div class="rank">{position}º resultado</div>', unsafe_allow_html=True)
        image_path = IMAGES_PATH / f"{result['gtin']}.jpg"
        try:
            with Image.open(image_path) as source:
                with source.convert("RGB") as image:
                    with make_preview(image) as preview:
                        st.image(preview, width="stretch", alt=result["product"])
        except (FileNotFoundError, OSError):
            st.info("A imagem deste produto não está disponível no catálogo local.")

        st.write(result["product"])
        st.caption(result["brand"])
        st.markdown(
            f'<div class="score">Similaridade · {result["similarity"]:.3f}</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"GTIN {result['gtin']}")


def main() -> None:
    st.set_page_config(page_title="Busca visual | PI IV", page_icon="🍪", layout="wide")
    st.markdown(STYLES, unsafe_allow_html=True)

    st.markdown(
        '<div class="hero-title">Analise o biscoito<br>pela embalagem.</div>'
        '<div class="hero-copy">Envie até duas fotos e descubra os três produtos '
        'da nossa base mais similares.</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-label">Envie suas imagens</div>', unsafe_allow_html=True)
    uploaded_files = st.file_uploader(
        "",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        max_upload_size=MAX_UPLOAD_MB,
    )
    st.caption(f"JPG, PNG ou WEBP - Até {MAX_UPLOAD_MB} MB por imagem - Comparação independente para cada foto")

    files = [(file.name, file.getvalue()) for file in uploaded_files]
    signature = tuple((name, sha256(content).hexdigest()) for name, content in files)
    if st.session_state.get("upload_signature") != signature:
        st.session_state["upload_signature"] = signature
        st.session_state.pop("search_results", None)

    prepared = []
    if len(files) > MAX_IMAGES:
        st.error("Envie no máximo duas imagens. Remova os arquivos extras para continuar.")
    elif files:
        try:
            prepared = prepare_uploads(files)
        except ValueError as error:
            st.error(str(error))

    try:
        if prepared:
            for column, item in zip(st.columns(len(prepared)), prepared):
                with column:
                    with st.container(border=True):
                        with make_preview(item.image) as preview:
                            st.image(preview, width="stretch", alt=f"Foto enviada: {item.name}")
                        st.caption(item.name)

        search_clicked = st.button(
            "Encontrar produtos similares",
            type="primary",
            disabled=not prepared,
            width="stretch",
        )
        if search_clicked:
            st.session_state.pop("search_results", None)
            if not DATABASE_PATH.is_file():
                st.error("A base de produtos ainda não foi preparada. Prepare o catálogo antes de iniciar a busca.")
            else:
                try:
                    with st.spinner("Comparando suas fotos com o catálogo..."):
                        stat = DATABASE_PATH.stat()
                        classifier, inference_lock = load_search_engine(
                            str(DATABASE_PATH), (stat.st_mtime_ns, stat.st_size),
                        )
                        with inference_lock:
                            results = [
                                {"name": item.name, "matches": classifier.predict_image(item.image, top_k=3)}
                                for item in prepared
                            ]
                        st.session_state["search_results"] = results
                except (OSError, RuntimeError, ValueError):
                    logger.exception("Falha ao comparar as imagens com a base de produtos.")
                    st.error("Não foi possível concluir a comparação. Confira a base de produtos e tente novamente.")

        results = st.session_state.get("search_results")
        if results:
            st.markdown('<div class="section-label">02 · Produtos mais similares</div>', unsafe_allow_html=True)
            st.caption("Quanto maior a similaridade, maior a proximidade visual. Esse valor não representa uma probabilidade de acerto.")
            for group in results:
                st.subheader(group["name"], anchor=False)
                matches = group["matches"]
                if not matches:
                    st.info("Nenhum produto foi encontrado para esta imagem.")
                    continue
                for position, (column, match) in enumerate(zip(st.columns(len(matches)), matches), start=1):
                    with column:
                        show_product(match, position)
        else:
            st.markdown(
                '<div class="empty-results"><strong></strong>'
                'Envie suas imagens e faça a comparação para ver os produtos aqui.</div>',
                unsafe_allow_html=True,
            )
        st.markdown('<div class="footer-note">PI IV</div>', unsafe_allow_html=True)
    finally:
        for item in prepared:
            item.image.close()

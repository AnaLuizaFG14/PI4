"""Executa a predição e permite solicitar o download das imagens ausentes."""

import argparse
from pathlib import Path

import pandas as pd

from src.modules.image_downloader import download_all_images


BASE_PATH = Path(__file__).resolve().parents[1]
PRODUCTS_PATH = BASE_PATH / "data/processed/products.csv"
IMAGES_PATH = BASE_PATH / "data/images"
DATABASE_PATH = BASE_PATH / "data/embeddings.pt"

BRANDS = ["Adria", "Bauducco"]
KEYWORDS = [
    "biscoito", "bisc", "bolacha", "cookie", "cookies", "wafer", "waffer",
    "cracker", "cream cracker", "tortinha", "tortinhas", "goiabinha",
    "recheadinho", "choco biscuit", "chocobiscuit", "chico biscuit",
]


def load_products(products_path: Path) -> pd.DataFrame:
    if products_path.is_file():
        print("Carregando os dados existentes...")
        return pd.read_csv(products_path, dtype={"gtin": "string"})

    from src.modules.api_client import OpenFoodFactsClient
    from src.modules.data_processing import ProductDataProcessor

    print("Buscando os produtos...")
    client = OpenFoodFactsClient()
    products = client.get_products(brands_list=BRANDS, key_words=KEYWORDS)
    df = ProductDataProcessor(brands=BRANDS).process(products)
    if df.empty:
        raise ValueError("A busca não retornou produtos válidos.")

    products_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(products_path, index=False)
    return df


def load_classifier(
    products_path: Path,
    images_path: Path,
    database_path: Path,
    *,
    batch_size: int = 16,
    rebuild: bool = False,
):
    from src.modules.image_encoder import ImageEncoder
    from src.modules.product_classifier import ProductClassifier

    print("Carregando o DINOv2...")
    encoder = ImageEncoder()
    classifier = ProductClassifier(encoder=encoder, database_path=database_path)

    if database_path.is_file() and not rebuild:
        print("Carregando a base de imagens existente...")
        classifier.load_database()
    else:
        print("Criando a base de imagens...")
        classifier.build_database(
            products_path=products_path,
            images_path=images_path,
            batch_size=batch_size,
        )

    return classifier


def main(
    image_path: str | Path,
    *,
    products_path: str | Path = PRODUCTS_PATH,
    images_path: str | Path = IMAGES_PATH,
    database_path: str | Path = DATABASE_PATH,
    top_k: int = 3,
    batch_size: int = 16,
    workers: int = 4,
    max_attempts: int = 10,
    retry_delay: float = 3,
    rebuild: bool = False,
    download_images: bool = False,
) -> list[dict]:
    image_path = Path(image_path)
    products_path = Path(products_path)
    images_path = Path(images_path)
    database_path = Path(database_path)

    if not image_path.is_file():
        raise FileNotFoundError(f"A imagem de consulta não existe: {image_path}")
    if min(top_k, batch_size, workers, max_attempts) < 1:
        raise ValueError("Os tamanhos, workers e max_attempts devem ser pelo menos 1.")
    if retry_delay < 0:
        raise ValueError("retry_delay não pode ser negativo.")

    # Uma base salva permite consultar produtos sem acessar o catálogo original.
    if download_images or rebuild or not database_path.is_file():
        df = load_products(products_path)
        if df.empty:
            raise ValueError("O CSV não contém produtos.")

        if download_images:
            downloaded = download_all_images(
                df=df,
                output_path=images_path,
                workers=workers,
                max_attempts=max_attempts,
                retry_delay=retry_delay,
            )

            if not all(downloaded):
                failed_gtins = df.loc[
                    [not success for success in downloaded], "gtin"
                ].tolist()
                raise RuntimeError(
                    f"Não foi possível baixar {len(failed_gtins)} imagem(ns) "
                    f"após {max_attempts} tentativas. GTINs pendentes: {failed_gtins}. "
                    "Execute novamente com --download-images para tentar as ausentes."
                )

    classifier = load_classifier(
        products_path=products_path,
        images_path=images_path,
        database_path=database_path,
        batch_size=batch_size,
        rebuild=rebuild,
    )
    return classifier.predict(image_path=image_path, top_k=top_k)


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Foto do produto a consultar.")
    parser.add_argument("--products", type=Path, default=PRODUCTS_PATH)
    parser.add_argument("--images", type=Path, default=IMAGES_PATH)
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-attempts", type=int, default=10)
    parser.add_argument("--retry-delay", type=float, default=3)
    parser.add_argument("--rebuild", action="store_true", help="Recria os vetores do catálogo.")
    parser.add_argument(
        "--download-images",
        action="store_true",
        help="Baixa as imagens ausentes somente quando esta opção é informada.",
    )
    args = parser.parse_args()

    try:
        results = main(
            image_path=args.image,
            products_path=args.products,
            images_path=args.images,
            database_path=args.database,
            top_k=args.top_k,
            batch_size=args.batch_size,
            workers=args.workers,
            max_attempts=args.max_attempts,
            retry_delay=args.retry_delay,
            rebuild=args.rebuild,
            download_images=args.download_images,
        )
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as error:
        parser.exit(status=1, message=f"Erro: {error}\n")

    for position, result in enumerate(results, start=1):
        print(
            f"{position}. {result['product']} | "
            f"Marca: {result['brand']} | "
            f"GTIN: {result['gtin']} | "
            f"Similaridade: {result['similarity']:.4f}"
        )


if __name__ == "__main__":
    cli()

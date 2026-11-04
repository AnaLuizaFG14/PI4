#%%
from pathlib import Path

from src.modules.api_client import OpenFoodFactsClient
from src.modules.data_processing import ProductDataProcessor

from src.modules.image_downloader import download_all_images

BRANDS = [
    "Adria",
    "Bauducco",
]

KEYWORDS = [
    "biscoito",
    "bisc",
    "bolacha",
    "cookie",
    "cookies",
    "wafer",
    "waffer",
    "cracker",
    "cream cracker",
    "tortinha",
    "tortinhas",
    "goiabinha",
    "recheadinho",
    "choco biscuit",
    "chocobiscuit",
    "chico biscuit",
]

PRODUCTS_PATH = Path("data/processed/products.csv")
IMAGES_PATH = Path("data/images")


def main():
    client = OpenFoodFactsClient()

    products = client.get_products(
        brands_list=BRANDS,
        key_words=KEYWORDS,
    )

    processor = ProductDataProcessor(
        brands=BRANDS
    )

    df = processor.process(products)

    PRODUCTS_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_csv(
        PRODUCTS_PATH,
        index=False
    )

    download_all_images(
        df=df,
        output_path=str(IMAGES_PATH)
    )


if __name__ == "__main__":
    main()
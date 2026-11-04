
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests
from PIL import Image


def _download_image(url: str,image_path: Path) -> bool:
    try:
        response = requests.get(url,timeout=(20, 20))
        response.raise_for_status()

        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        image.save(image_path)

        return True

    except (requests.exceptions.RequestException,OSError):
        return False


def _download_product_image(item: pd.Series,output_path: Path) -> bool:

    image_url = item["image_url"]
    gtin = item["gtin"]

    image_path = output_path / f"{gtin}.jpg"

    if image_path.exists():
        return True

    return _download_image(url=image_url,image_path=image_path)


def download_all_images(df: pd.DataFrame,
                        output_path: str | Path,
                        workers: int = 4
                        ) -> list[bool]:

    output_path = Path(output_path)

    output_path.mkdir(parents=True,exist_ok=True)

    items = [row for _, row in df.iterrows()]

    with ThreadPoolExecutor(max_workers=workers) as executor:

        results = list(
            executor.map(
                lambda row: _download_product_image(
                    item=row,
                    output_path=output_path),
                items
            )
        )

    return results
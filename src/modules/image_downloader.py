import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests
from PIL import Image
from time import sleep


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

    if image_path.is_file():
        return True

    return _download_image(url=image_url,image_path=image_path)


def download_all_images(
    df: pd.DataFrame,
    output_path: str | Path,
    workers: int = 4,
    max_attempts: int = 5,
    retry_delay: float = 2,
) -> list[bool]:

    if max_attempts < 1:
        raise ValueError("max_attempts deve ser pelo menos 1.")

    if retry_delay < 0:
        raise ValueError("retry_delay não pode ser negativo.")

    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    items = [row for _, row in df.iterrows()]

    results = [
        (output_path / f"{str(item['gtin']).strip()}.jpg").is_file()
        for item in items
    ]

    pending = [
        (index, item)
        for index, item in enumerate(items)
        if not results[index]
    ]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for attempt in range(1, max_attempts + 1):
            if not pending:
                break

            print(
                f"Tentativa {attempt}/{max_attempts}: "
                f"{len(pending)} imagem(ns) pendente(s)."
            )

            attempt_results = list(
                executor.map(
                    lambda entry: _download_product_image(
                        item=entry[1],
                        output_path=output_path,
                    ),
                    pending,
                )
            )

            for (index, _), success in zip(pending, attempt_results):
                results[index] = success

            pending = [
                (index, item)
                for index, item in pending
                if not results[index]
            ]

            if pending and attempt < max_attempts:
                sleep(retry_delay)

    return results
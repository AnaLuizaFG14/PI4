from pathlib import Path

import pandas as pd
import torch
from PIL import Image

from .image_encoder import ImageEncoder


class ProductClassifier:
    def __init__(
        self,
        encoder: ImageEncoder,
        database_path: str | Path = "data/embeddings.pt",
    ):
        self.encoder = encoder
        self.database_path = Path(database_path)
        self.embeddings = None
        self.metadata = None

    @staticmethod
    def _read_image(image_path: str | Path) -> Image.Image:
        with Image.open(image_path) as image:
            return image.convert("RGB")

    def build_database(
        self,
        products_path: str | Path,
        images_path: str | Path,
        batch_size: int = 16,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size deve ser pelo menos 1.")

        df = pd.read_csv(products_path, dtype={"gtin": "string"})
        required_columns = {"gtin", "product", "image_brand"}
        missing_columns = required_columns.difference(df.columns)
        if missing_columns:
            raise ValueError(f"Colunas ausentes no CSV: {sorted(missing_columns)}")

        df["gtin"] = df["gtin"].str.strip()
        if df["gtin"].isna().any() or df["gtin"].eq("").any():
            raise ValueError("O CSV contém produtos sem GTIN.")

        df = df.drop_duplicates(subset="gtin").reset_index(drop=True)
        if df.empty:
            raise ValueError("O CSV não contém produtos.")

        images_path = Path(images_path)
        paths = [images_path / f"{gtin}.jpg" for gtin in df["gtin"]]
        available = [path.is_file() for path in paths]
        missing_count = len(paths) - sum(available)
        df = df.loc[available].reset_index(drop=True)
        paths = [path for path, exists in zip(paths, available) if exists]

        if not paths:
            raise FileNotFoundError(
                "Nenhuma imagem do catálogo está disponível. "
                "Use download_images=True para solicitar o download."
            )
        if missing_count:
            print(f"Ignorando {missing_count} produto(s) sem imagem local.")

        embeddings = []
        for start in range(0, len(paths), batch_size):
            images = []
            try:
                for path in paths[start:start + batch_size]:
                    images.append(self._read_image(path))
                embeddings.append(self.encoder.encode(images))
            finally:
                for image in images:
                    image.close()

            processed = min(start + batch_size, len(paths))
            print(f"Imagens processadas: {processed}/{len(paths)}")

        self.embeddings = torch.cat(embeddings, dim=0)
        self.metadata = (
            df[["gtin", "product", "image_brand"]]
            .rename(columns={"image_brand": "brand"})
            .fillna("")
            .astype(str)
            .to_dict("records")
        )

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "model_name": self.encoder.model_name,
                "embeddings": self.embeddings,
                "metadata": self.metadata,
            },
            self.database_path,
        )

    def load_database(self) -> None:
        database = torch.load(
            self.database_path,
            map_location="cpu",
            weights_only=True,
        )

        if database.get("model_name") != self.encoder.model_name:
            raise ValueError(
                "A base usa outro modelo ou um formato anterior. "
                "Execute app.py com --rebuild para recriá-la."
            )

        embeddings = database["embeddings"]
        metadata = database["metadata"]
        if embeddings.ndim != 2 or len(metadata) != embeddings.shape[0] or not metadata:
            raise ValueError("A base de imagens está vazia ou inconsistente.")

        self.embeddings = embeddings
        self.metadata = metadata

    def predict(self, image_path: str | Path, top_k: int = 3) -> list[dict]:
        with self._read_image(image_path) as image:
            return self.predict_image(image=image, top_k=top_k)

    @torch.inference_mode()
    def predict_image(self, image: Image.Image, top_k: int = 3) -> list[dict]:
        """Consulta uma imagem já aberta, sem gravar o upload no disco."""
        if self.embeddings is None or self.metadata is None:
            raise RuntimeError("Crie ou carregue a base antes de fazer uma predição.")
        if top_k < 1:
            raise ValueError("top_k deve ser pelo menos 1.")

        query_embedding = self.encoder.encode([image])

        similarities = (query_embedding @ self.embeddings.T).squeeze(0)
        values, indices = torch.topk(
            similarities,
            k=min(top_k, len(self.metadata)),
        )

        return [
            {
                **self.metadata[int(index.item())],
                "similarity": value.item(),
            }
            for value, index in zip(values, indices)
        ]

import pandas as pd

class ProductDataProcessor:

    def __init__(self, brands: list[str]):
        self.brands = brands

    @staticmethod
    def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df.columns = (
            df.columns
            .str.lower()
            .str.replace(".", "_", regex=False)
            .str.replace("-", "_", regex=False)
        )

        return df

    def _normalize_brands(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df["image_brand"] = (
            df["image_brand"]
            .fillna("")
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace(".", "", regex=False)
            .str.lower()
        )

        def find_brand(row) -> str:
            image_brand = str(row["image_brand"]).lower()
            product = str(row["product"]).lower()

            brand = next(
                (
                    brand.title()
                    for brand in self.brands
                    if brand.lower() in image_brand
                ),
                None
            )

            if brand:
                return brand

            return next(
                (
                    brand.title()
                    for brand in self.brands
                    if brand.lower() in product
                ),
                ""
            )

        df["image_brand"] = df.apply(find_brand, axis=1)

        return df

    @staticmethod
    def _normalize_products(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df["product"] = (
            df["product"]
            .fillna("")
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace(".", "", regex=False)
            .str.lower()
        )

        return df

    @staticmethod
    def _select_columns(
        df: pd.DataFrame,
        nutriments_cols: list[str] | None = None
    ) -> pd.DataFrame:

        base_cols = [
            "image_url",
            "gtin",
            "product",
            "image_brand",
            "categories",
        ]

        if nutriments_cols is None:
            nutriments_cols = [
                "nutriments_energy_kcal_100g",
                "nutriments_carbohydrates_100g",
                "nutriments_sugars_100g",
                "nutriments_fat_100g",
                "nutriments_saturated_fat_100g",
                "nutriments_fiber_100g",
                "nutriments_proteins_100g",
                "nutriments_sodium_100g",
            ]

        columns = base_cols + nutriments_cols

        return df.loc[:, columns].copy()

    def process(
        self,
        products: list[dict],
        nutriments_cols: list[str] | None = None
    ) -> pd.DataFrame:

        df = pd.json_normalize(products)

        if df.empty:
            return df

        df = self._normalize_columns(df)
        df = self._normalize_brands(df)
        df = self._normalize_products(df)
        df = self._select_columns(df, nutriments_cols)

        df = df.fillna(0)

        df = df.drop_duplicates(
            subset="gtin",
            keep="first"
        )

        return df
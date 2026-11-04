import time
from requests.exceptions import HTTPError

import openfoodfacts

class OpenFoodFactsClient:

    def __init__(self, user_agent: str = "PI-IV"):
        self.api = openfoodfacts.API(user_agent=user_agent)

    def _search_products_by_brand(self,
                                  brands_list: list[str],
                                  page_size: int = 50,
                                  max_attempts: int = 5,
                                  request_delay: float = 5,
                                  page_delay: float = 2
                                  ) -> list[dict]:

        all_products = []

        if not brands_list:
            return all_products

        for brand in brands_list:
            page = 1

            while True:
                products_page = None

                for attempt in range(1, max_attempts + 1):
                    try:
                        response = self.api.product.text_search(
                            brand,
                            page=page,
                            page_size=page_size,
                        )

                        products_page = response.get("products", [])
                        break

                    except HTTPError as e:
                        # print(
                        #     f"Brand: {brand} | "
                        #     f"Page: {page} | "
                        #     f"Attempt: {attempt}/{max_attempts} | "
                        #     f"Error: {e}"
                        # )

                        if attempt < max_attempts:
                            time.sleep(request_delay)

                if products_page is None:
                    # print(f"Skipping brand {brand}, page {page}")
                    break

                if not products_page:
                    break

                all_products.extend(products_page)

                if len(products_page) < page_size:
                    break

                page += 1
                time.sleep(page_delay)

        return all_products

    @staticmethod
    def _filter_products(products: list[dict],
                         key_words: list[str] | None = None
                         ) -> list[dict]:

        keywords = [
            word.strip().lower()
            for word in (key_words or [])
            if word.strip()
        ]

        filtered_products = []
        seen_gtins = set()

        for product in products:
            product_name = (product.get("product_name") or "").lower()
            countries = product.get("countries_tags") or []
            image_url = product.get("image_front_url")
            gtin = product.get("code")

            if (
                "en:brazil" not in countries
                or not image_url
                or (keywords and not any(
                    word in product_name for word in keywords
                ))
            ):
                continue

            if gtin and gtin in seen_gtins:
                continue

            if gtin:
                seen_gtins.add(gtin)

            filtered_products.append({
                "image_url": image_url,
                "gtin": gtin,
                "product": product.get("product_name"),
                "image_brand": product.get("brands"),
                "categories": product.get("categories_tags"),
                "nutriments": product.get("nutriments"),
            })

        return filtered_products

    def get_products(self,
                     brands_list: list[str],
                     key_words: list[str] | None = None,
                     page_size: int = 50,
                     max_attempts: int = 5,
                     request_delay: float = 5,
                     page_delay: float = 2
                     ) -> list[dict]:

        products = self._search_products_by_brand(
            brands_list=brands_list,
            page_size=page_size,
            max_attempts=max_attempts,
            request_delay=request_delay,
            page_delay=page_delay,
        )

        return self._filter_products(products, key_words)
"""Validação e preparo das fotos enviadas pela interface."""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


MAX_IMAGES = 2
MAX_UPLOAD_MB = 10
MAX_IMAGE_PIXELS = 25_000_000


@dataclass
class UploadedProductImage:
    name: str
    image: Image.Image


def prepare_uploads(files: list[tuple[str, bytes]]) -> list[UploadedProductImage]:
    if not 1 <= len(files) <= MAX_IMAGES:
        raise ValueError("Envie uma ou duas imagens para comparar.")

    prepared = []
    try:
        for name, content in files:
            if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
                raise ValueError(f"{name}: o tamanho máximo por imagem é {MAX_UPLOAD_MB} MB.")
            try:
                with Image.open(BytesIO(content)) as source:
                    if source.format not in {"JPEG", "PNG", "WEBP"}:
                        raise ValueError(f"{name}: use uma imagem JPG, PNG ou WEBP.")
                    if source.width * source.height > MAX_IMAGE_PIXELS:
                        raise ValueError(f"{name}: reduza a resolução da imagem e tente novamente.")
                    image = ImageOps.exif_transpose(source).convert("RGB")
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
                raise ValueError(f"Não foi possível abrir {name}. Envie uma imagem válida.") from error
            prepared.append(UploadedProductImage(name=name, image=image))
        return prepared
    except Exception:
        for item in prepared:
            item.image.close()
        raise


def make_preview(image: Image.Image, size: tuple[int, int] = (640, 420)) -> Image.Image:
    """Mantém a proporção da embalagem em uma área de exibição uniforme."""
    fitted = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "white")
    canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    fitted.close()
    return canvas

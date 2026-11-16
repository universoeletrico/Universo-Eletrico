"""Preparação segura de imagens manuais para a biblioteca do Studio."""
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def normalize_post_image(payload: bytes) -> bytes:
    """Valida a imagem e converte para JPEG 1080x1350, sem distorção."""
    if not payload or len(payload) > MAX_IMAGE_BYTES:
        raise ValueError("A imagem deve ter até 5 MB.")
    try:
        with Image.open(BytesIO(payload)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("Use JPG, PNG ou WEBP.")
            if source.width * source.height > MAX_PIXELS:
                raise ValueError("A imagem tem resolução excessiva.")
            source.load()
            if source.width < 540 or source.height < 675:
                raise ValueError("Envie uma arte de pelo menos 540 × 675 pixels.")
            # O padding evita cortar texto do criativo.
            rgb = ImageOps.exif_transpose(source).convert("RGB")
            output = ImageOps.pad(rgb, (1080, 1350), method=Image.Resampling.LANCZOS,
                                  color=(12, 32, 58), centering=(0.5, 0.5))
            buf = BytesIO()
            output.save(buf, format="JPEG", quality=91, optimize=True)
            return buf.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Arquivo de imagem inválido ou incompatível.") from exc

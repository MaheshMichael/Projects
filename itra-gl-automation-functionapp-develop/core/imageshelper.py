import base64
import os
from typing import Optional

from azure.storage.blob.aio import ContainerClient
from typing_extensions import Literal, Required, TypedDict

from ..approaches.approach import Document


class ImageURL(TypedDict, total=False):
    url: Required[str]
    """Either a URL of the image or the base64 encoded image data."""

    detail: Literal["auto", "low", "high"]
    """Specifies the detail level of the image."""


async def download_blob_as_base64(blob_container_client: ContainerClient, file_path: str) -> Optional[str]:
    base_name, _ = os.path.splitext(file_path)
    blob = await blob_container_client.get_blob_client(base_name + ".png").download_blob()

    if not blob.properties:
        return None
    img = base64.b64encode(await blob.readall()).decode("utf-8")
    return f"data:image/png;base64,{img}"


async def fetch_image(blob_container_client: ContainerClient, result: Document) -> Optional[ImageURL]:
    if result.sourcepage:
        img = await download_blob_as_base64(blob_container_client, result.sourcepage)
        if img:
            return {"url": img, "detail": "auto"}
        else:
            return None
    return None

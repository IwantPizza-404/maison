"""Фото товаров по ссылкам — для импорта из Excel.

- Ссылки Google Drive и Dropbox превращаются в прямые ссылки на файл.
- Фото с нашего же сайта не скачиваются, а читаются из хранилища.
- Ссылки на внутренние адреса (localhost, 10.x, 192.168.x…) запрещены: сервер не должен
  ходить по ссылкам из файла в свою внутреннюю сеть.
"""

import ipaddress
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models.fields.files import FieldFile
from django.utils.translation import gettext as _
from PIL import Image, UnidentifiedImageError

from apps.core.images import MAX_UPLOAD_MB

MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024
TIMEOUT = 20
MAX_REDIRECTS = 3
PARALLEL_DOWNLOADS = 8
FORMAT_EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "HEIF": "heic"}
GOOGLE_DRIVE_ID = re.compile(r"/file/d/([\w-]+)")


class PhotoError(Exception):
    """Фото нельзя использовать — текст показывается в отчёте импорта."""


@dataclass(frozen=True)
class Photo:
    content: bytes
    extension: str


def absolute_url(field: FieldFile) -> str:
    """Полная ссылка на файл: локально MEDIA_URL относительный (/media/…)."""
    return urljoin(settings.BACKEND_URL.rstrip("/") + "/", field.url)


def direct_link(url: str) -> str:
    """Ссылка «поделиться» из Google Drive / Dropbox → ссылка на сам файл."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host == "drive.google.com":
        match = GOOGLE_DRIVE_ID.search(parts.path)
        file_id = match.group(1) if match else dict(parse_qsl(parts.query)).get("id")
        if file_id:
            return f"https://drive.google.com/uc?export=download&id={file_id}"
    if host.endswith("dropbox.com"):
        query = {**dict(parse_qsl(parts.query)), "dl": "1"}
        return urlunsplit(parts._replace(query=urlencode(query)))
    return url


def check_public_host(host: str | None) -> None:
    if not host:
        raise PhotoError(_("invalid link"))
    try:
        addresses = {str(info[4][0]) for info in socket.getaddrinfo(host, None)}
    except socket.gaierror as exc:
        raise PhotoError(_("site %(host)s not found") % {"host": host}) from exc
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if not ip.is_global:
            raise PhotoError(_("links to internal addresses are not allowed"))


def to_photo(data: bytes) -> Photo:
    """Проверяет, что байты — изображение допустимого формата."""
    if len(data) > MAX_BYTES:
        raise PhotoError(_("file is larger than %(mb)s MB") % {"mb": MAX_UPLOAD_MB})
    try:
        image = Image.open(BytesIO(data))
        image_format = image.format or ""
        image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise PhotoError(_("the link does not lead to an image")) from exc
    extension = FORMAT_EXTENSIONS.get(image_format)
    if extension is None:
        raise PhotoError(_("format %(format)s is not supported") % {"format": image_format})
    return Photo(data, extension)


def download(url: str) -> Photo:
    url = direct_link(url)
    try:
        for _redirect in range(MAX_REDIRECTS + 1):
            parts = urlsplit(url)
            if parts.scheme not in {"http", "https"}:
                raise PhotoError(_("the link must start with http:// or https://"))
            check_public_host(parts.hostname)
            # Редиректы проходим сами, чтобы проверить адрес каждого шага
            with httpx.stream(
                "GET", url, timeout=TIMEOUT, headers={"User-Agent": "Maison"}
            ) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                if response.status_code != 200:
                    raise PhotoError(
                        _("the site responded with error %(code)s") % {"code": response.status_code}
                    )
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise PhotoError(_("file is larger than %(mb)s MB") % {"mb": MAX_UPLOAD_MB})
                return to_photo(bytes(data))
        raise PhotoError(_("too many redirects"))
    except httpx.HTTPError as exc:
        raise PhotoError(_("could not download the file")) from exc


def read_stored(name: str) -> Photo:
    with default_storage.open(name, "rb") as file:
        return to_photo(file.read())


class PhotoFetcher:
    """Скачивает все ссылки файла заранее и параллельно — импорт укладывается в таймаут запроса.

    own_files — фото с нашего сайта: полная ссылка → имя файла в хранилище.
    """

    def __init__(self, own_files: dict[str, str]) -> None:
        self.own_files = own_files
        self.results: dict[str, Photo | PhotoError] = {}

    def fetch_one(self, url: str) -> Photo | PhotoError:
        try:
            if url in self.own_files:
                return read_stored(self.own_files[url])
            return download(url)
        except PhotoError as exc:
            return exc

    def prefetch(self, urls: set[str]) -> None:
        todo = sorted(urls - self.results.keys())
        with ThreadPoolExecutor(max_workers=PARALLEL_DOWNLOADS) as pool:
            for url, result in zip(todo, pool.map(self.fetch_one, todo), strict=True):
                self.results[url] = result

    def get(self, url: str) -> Photo:
        if url not in self.results:
            self.results[url] = self.fetch_one(url)
        result = self.results[url]
        if isinstance(result, PhotoError):
            raise result
        return result

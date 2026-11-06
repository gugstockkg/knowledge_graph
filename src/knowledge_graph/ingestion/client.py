"""Small standard-library OpenDART API client."""

from __future__ import annotations

import json
import os
import ssl
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO
from xml.etree import ElementTree
from typing import Any

API_BASE = "https://opendart.fss.or.kr/api"


class DartApiError(RuntimeError):
    """An HTTP or OpenDART application-level error."""

    def __init__(self, message: str, *, status: str | None = None) -> None:
        super().__init__(message)
        self.status = status


class DartClient:
    def __init__(self, api_key: str | None = None, *, timeout: float = 60.0, delay: float = 0.15):
        self.api_key = api_key or os.environ.get("OPENDART_API_KEY")
        if not self.api_key:
            raise DartApiError("OPENDART_API_KEY 환경변수를 설정하세요.")
        self.timeout = timeout
        self.delay = max(0.0, delay)
        self._last_request = 0.0
        # Use a verified system CA bundle when available, including macOS Python.
        bundle=os.environ.get('SSL_CERT_FILE')
        if not bundle and Path('/etc/ssl/cert.pem').exists():bundle='/etc/ssl/cert.pem'
        self.ssl_context=ssl.create_default_context(cafile=bundle)

    def _wait(self) -> None:
        remaining = self.delay - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)

    def _request(self, endpoint: str, params: dict[str, Any]) -> bytes:
        self._wait()
        query = {key: str(value) for key, value in params.items() if value is not None}
        query["crtfc_key"] = self.api_key or ""
        url = f"{API_BASE}/{endpoint}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(url, headers={"User-Agent": "GUG-OpenDART-KG/0.1"})
        self._last_request = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            detail=detail.replace(self.api_key or '', '[REDACTED]')
            raise DartApiError(f"OpenDART HTTP {exc.code}: {detail[:500]}") from None
        except urllib.error.URLError as exc:
            reason=str(exc.reason).replace(self.api_key or '', '[REDACTED]')
            raise DartApiError(f"OpenDART 연결 오류: {reason}") from None

    def get_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        body = self._request(endpoint, params)
        try:
            result = json.loads(body.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DartApiError(f"{endpoint} 응답을 JSON으로 읽지 못했습니다.") from exc
        if not isinstance(result, dict):
            raise DartApiError(f"{endpoint} 응답이 객체 형식이 아닙니다.")
        status = str(result.get("status", ""))
        if status not in {"000", "013"}:
            raise DartApiError(
                f"OpenDART {endpoint} 오류 {status}: {result.get('message', '알 수 없는 오류')}",
                status=status,
            )
        return result

    def download_document(self, receipt_no: str) -> bytes:
        body = self._request("document.xml", {"rcept_no": receipt_no})
        if body.startswith(b"PK\x03\x04"):
            try:
                with zipfile.ZipFile(BytesIO(body)) as archive:
                    if archive.testzip() is not None or not any(n.lower().endswith('.xml') for n in archive.namelist()):
                        raise DartApiError('원문 ZIP에 유효한 XML이 없습니다.')
            except zipfile.BadZipFile:
                raise DartApiError('원문 ZIP이 손상되었습니다.') from None
            return body
        try:
            result = json.loads(body.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            try:
                root=ElementTree.fromstring(body)
                status=root.findtext('status') or ''
                message=root.findtext('message') or '문서 다운로드 실패'
            except ElementTree.ParseError:
                raise DartApiError('원문 응답이 유효한 ZIP 또는 오류 응답이 아닙니다.') from None
            raise DartApiError(f'공시 원문 오류 {status}: {message}',status=status) from None
        status = str(result.get("status", "")) if isinstance(result, dict) else ""
        message = result.get("message", "문서 다운로드 실패") if isinstance(result, dict) else "문서 다운로드 실패"
        raise DartApiError(f"공시 원문 {receipt_no} 오류 {status}: {message}", status=status)

    def download_company_codes(self) -> tuple[bytes, list[dict[str, str]]]:
        body = self._request("corpCode.xml", {})
        try:
            with zipfile.ZipFile(BytesIO(body)) as archive:
                xml_names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
                if not xml_names:
                    raise DartApiError("고유번호 응답 ZIP에 XML 파일이 없습니다.")
                root = ElementTree.fromstring(archive.read(xml_names[0]))
        except (zipfile.BadZipFile, ElementTree.ParseError) as exc:
            raise DartApiError("고유번호 파일을 ZIP/XML로 해석하지 못했습니다.") from exc
        companies: list[dict[str, str]] = []
        for item in root.findall("list"):
            company = {child.tag: (child.text or "").strip() for child in item}
            if company.get("corp_code"):
                companies.append(company)
        return body, companies

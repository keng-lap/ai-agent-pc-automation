"""Search Microsoft's signed WinGet source2 index without invoking winget.exe."""

from __future__ import annotations

import ctypes
import hashlib
import io
import os
import re
import sqlite3
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import requests
from pydantic import BaseModel, ConfigDict

WINGET_SOURCE2_URL = "https://cdn.winget.microsoft.com/cache/source2.msix"
EXPECTED_PACKAGE_NAME = "Microsoft.Winget.Source"
EXPECTED_PUBLISHER = (
    "CN=Microsoft Corporation, O=Microsoft Corporation, L=Redmond, "
    "S=Washington, C=US"
)
MAX_MSIX_BYTES = 250 * 1024 * 1024
MAX_INDEX_DB_BYTES = 512 * 1024 * 1024
MAX_APPX_MANIFEST_BYTES = 1_000_000
MAX_SEARCH_RESULTS = 20
CACHE_TTL_SECONDS = 3600
USER_AGENT = "ai-agent-pc-automation-catalog/1.0"
QUERY_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]{2,128}$")


class CatalogUnavailable(RuntimeError):
    """The signed Microsoft catalog could not be loaded or trusted."""


class CatalogCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    package_id: str
    name: str
    moniker: str | None
    latest_version: str


class CatalogSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: str = "CATALOG_MATCHES"
    source: str = "microsoft-winget-source2"
    source_version: str
    source_sha256: str
    checked_at: str
    candidates: tuple[CatalogCandidate, ...]


class WindowsMsixSignatureVerifier:
    """Use WinVerifyTrust and, when requested, extract the verified signer subject."""

    def verify(self, package_path: Path) -> bool:
        trusted, _subject = self._verify_and_read_signer(package_path, include_subject=False)
        return trusted

    def verify_and_get_signer_subject(self, package_path: Path) -> str | None:
        """Return the subject of the primary signer only after WinVerifyTrust succeeds."""
        trusted, subject = self._verify_and_read_signer(package_path, include_subject=True)
        return subject if trusted else None

    @staticmethod
    def _verify_and_read_signer(
        package_path: Path,
        *,
        include_subject: bool,
    ) -> tuple[bool, str | None]:
        if os.name != "nt" or not package_path.is_file():
            return False, None

        class _Guid(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        class _WinTrustFileInfo(ctypes.Structure):
            _fields_ = [
                ("cbStruct", ctypes.c_uint32),
                ("pcwszFilePath", ctypes.c_wchar_p),
                ("hFile", ctypes.c_void_p),
                ("pgKnownSubject", ctypes.POINTER(_Guid)),
            ]

        class _WinTrustData(ctypes.Structure):
            _fields_ = [
                ("cbStruct", ctypes.c_uint32),
                ("pPolicyCallbackData", ctypes.c_void_p),
                ("pSIPClientData", ctypes.c_void_p),
                ("dwUIChoice", ctypes.c_uint32),
                ("fdwRevocationChecks", ctypes.c_uint32),
                ("dwUnionChoice", ctypes.c_uint32),
                ("pFile", ctypes.POINTER(_WinTrustFileInfo)),
                ("dwStateAction", ctypes.c_uint32),
                ("hWVTStateData", ctypes.c_void_p),
                ("pwszURLReference", ctypes.c_wchar_p),
                ("dwProvFlags", ctypes.c_uint32),
                ("dwUIContext", ctypes.c_uint32),
                ("pSignatureSettings", ctypes.c_void_p),
            ]

        class _CryptProviderCertPrefix(ctypes.Structure):
            _fields_ = [
                ("cbStruct", ctypes.c_uint32),
                ("pCert", ctypes.c_void_p),
            ]

        action = _Guid.from_buffer_copy(
            uuid.UUID("00AAC56B-CD44-11D0-8CC2-00C04FC295EE").bytes_le
        )
        file_info = _WinTrustFileInfo()
        file_info.cbStruct = ctypes.sizeof(_WinTrustFileInfo)
        file_info.pcwszFilePath = str(package_path)

        trust_data = _WinTrustData()
        trust_data.cbStruct = ctypes.sizeof(_WinTrustData)
        trust_data.dwUIChoice = 2  # WTD_UI_NONE
        trust_data.fdwRevocationChecks = 1  # WTD_REVOKE_WHOLECHAIN
        trust_data.dwUnionChoice = 1  # WTD_CHOICE_FILE
        trust_data.dwStateAction = 1  # WTD_STATEACTION_VERIFY
        trust_data.dwProvFlags = 0x1000  # WTD_CACHE_ONLY_URL_RETRIEVAL
        trust_data.pFile = ctypes.pointer(file_info)

        wintrust = None
        trusted = False
        subject = None
        try:
            wintrust = ctypes.WinDLL("wintrust", use_last_error=True)
            verify = wintrust.WinVerifyTrust
            verify.restype = ctypes.c_long
            verify.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_Guid),
                ctypes.POINTER(_WinTrustData),
            ]
            trusted = verify(
                ctypes.c_void_p(-1),
                ctypes.byref(action),
                ctypes.byref(trust_data),
            ) == 0
            if not trusted or not include_subject:
                return trusted, None

            # These documented WinTrust helpers expose the signer certificate
            # from the state created by the successful WinVerifyTrust call.
            get_provider_data = wintrust.WTHelperProvDataFromStateData
            get_provider_data.restype = ctypes.c_void_p
            get_provider_data.argtypes = [ctypes.c_void_p]
            provider_data = get_provider_data(trust_data.hWVTStateData)
            if not provider_data:
                return False, None

            get_signer = wintrust.WTHelperGetProvSignerFromChain
            get_signer.restype = ctypes.c_void_p
            get_signer.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_int,
                ctypes.c_uint32,
            ]
            signer = get_signer(provider_data, 0, 0, 0)
            if not signer:
                return False, None

            get_provider_cert = wintrust.WTHelperGetProvCertFromChain
            get_provider_cert.restype = ctypes.c_void_p
            get_provider_cert.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            provider_cert = get_provider_cert(signer, 0)
            if not provider_cert:
                return False, None

            cert_context = ctypes.cast(
                provider_cert,
                ctypes.POINTER(_CryptProviderCertPrefix),
            ).contents.pCert
            if not cert_context:
                return False, None

            crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
            get_name = crypt32.CertGetNameStringW
            get_name.restype = ctypes.c_uint32
            get_name.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.c_wchar_p,
                ctypes.c_uint32,
            ]
            x500_name_format = ctypes.c_uint32(3)  # CERT_X500_NAME_STR
            required = get_name(
                cert_context,
                2,
                0,
                ctypes.byref(x500_name_format),
                None,
                0,
            )  # CERT_NAME_RDN_TYPE
            if required < 2 or required > 1024:
                return False, None
            buffer = ctypes.create_unicode_buffer(required)
            written = get_name(
                cert_context,
                2,
                0,
                ctypes.byref(x500_name_format),
                buffer,
                required,
            )
            if written != required:
                return False, None
            subject = buffer.value.strip()
            if not subject or len(subject) > 1000:
                return False, None
            return True, subject
        except (AttributeError, OSError, TypeError, ValueError):
            return False, None
        finally:
            if wintrust is not None:
                trust_data.dwStateAction = 2  # WTD_STATEACTION_CLOSE
                try:
                    wintrust.WinVerifyTrust(
                        ctypes.c_void_p(-1),
                        ctypes.byref(action),
                        ctypes.byref(trust_data),
                    )
                except (AttributeError, OSError, TypeError, ValueError):
                    pass


class MicrosoftWinGetCatalogIndex:
    """Download, verify and search Microsoft's source2.msix SQLite catalog."""

    def __init__(
        self,
        *,
        http_get=None,
        signature_verifier=None,
        monotonic_clock=None,
        utc_clock=None,
    ) -> None:
        self._http_get = http_get or requests.get
        self._signature_verifier = signature_verifier or WindowsMsixSignatureVerifier()
        self._monotonic = monotonic_clock or time.monotonic
        self._utc_clock = utc_clock or _utc_now_iso
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None
        self._expires_at = 0.0
        self._source_version = ""
        self._source_sha256 = ""
        self._checked_at = ""
        self._source_signer_subject: str | None = None

    @property
    def source_signer_subject(self) -> str | None:
        """Signer subject extracted from the verified source package, when available."""
        return self._source_signer_subject

    def search(self, query: str, *, limit: int = 10) -> CatalogSearchResponse:
        normalized = _validate_query(query)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_SEARCH_RESULTS:
            raise ValueError("limit must be between 1 and 20")

        with self._lock:
            if self._connection is None or self._monotonic() >= self._expires_at:
                self._refresh()

            assert self._connection is not None
            rows = self._connection.execute(
                """
                SELECT id, name, moniker, latest_version
                FROM packages
                WHERE instr(lower(name), lower(?)) > 0
                   OR instr(lower(id), lower(?)) > 0
                   OR instr(lower(COALESCE(moniker, '')), lower(?)) > 0
                ORDER BY
                    CASE
                        WHEN lower(name) = lower(?) OR lower(id) = lower(?) THEN 0
                        WHEN substr(lower(name), 1, length(?)) = lower(?) THEN 1
                        ELSE 2
                    END,
                    name COLLATE NOCASE,
                    id COLLATE NOCASE
                LIMIT ?
                """,
                (
                    normalized,
                    normalized,
                    normalized,
                    normalized,
                    normalized,
                    normalized,
                    normalized,
                    limit,
                ),
            ).fetchall()

            candidates = tuple(
                CatalogCandidate(
                    package_id=row[0],
                    name=row[1],
                    moniker=row[2],
                    latest_version=row[3],
                )
                for row in rows
                if isinstance(row[0], str)
                and isinstance(row[1], str)
                and (row[2] is None or isinstance(row[2], str))
                and isinstance(row[3], str)
            )
            return CatalogSearchResponse(
                source_version=self._source_version,
                source_sha256=self._source_sha256,
                checked_at=self._checked_at,
                candidates=candidates,
            )

    def _refresh(self) -> None:
        temp_path: Path | None = None
        connection: sqlite3.Connection | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="aiagent-winget-catalog-",
                suffix=".msix",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                digest = hashlib.sha256()
                total = 0
                response = self._http_get(
                    WINGET_SOURCE2_URL,
                    headers={
                        "Accept": "application/octet-stream",
                        "User-Agent": USER_AGENT,
                    },
                    timeout=(5.0, 30.0),
                    allow_redirects=False,
                    stream=True,
                )
                try:
                    if response.status_code != 200:
                        raise CatalogUnavailable("Microsoft catalog download was unsuccessful")
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > MAX_MSIX_BYTES:
                        raise CatalogUnavailable("Microsoft catalog exceeded its size limit")
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > MAX_MSIX_BYTES:
                            raise CatalogUnavailable("Microsoft catalog exceeded its size limit")
                        digest.update(chunk)
                        temp_file.write(chunk)
                finally:
                    close = getattr(response, "close", None)
                    if callable(close):
                        close()

            if not temp_path.exists() or temp_path.stat().st_size == 0:
                raise CatalogUnavailable("Microsoft catalog download was empty")
            if not self._signature_verifier.verify(temp_path):
                raise CatalogUnavailable("Microsoft catalog MSIX signature did not pass Windows trust validation")
            extract_subject = getattr(self._signature_verifier, "verify_and_get_signer_subject", None)
            self._source_signer_subject = extract_subject(temp_path) if callable(extract_subject) else None
            package_bytes = temp_path.read_bytes()
            if (
                len(package_bytes) != total
                or hashlib.sha256(package_bytes).hexdigest() != digest.hexdigest()
            ):
                raise CatalogUnavailable("Microsoft catalog changed after signature validation")

            with zipfile.ZipFile(io.BytesIO(package_bytes), "r") as archive:
                archive_names = archive.namelist()
                names = set(archive_names)
                if len(names) != len(archive_names):
                    raise CatalogUnavailable("Microsoft catalog archive contained duplicate paths")
                if not {
                    "AppxManifest.xml",
                    "AppxBlockMap.xml",
                    "AppxSignature.p7x",
                }.issubset(names):
                    raise CatalogUnavailable("Microsoft catalog package structure was incomplete")

                manifest_info = archive.getinfo("AppxManifest.xml")
                if manifest_info.file_size > MAX_APPX_MANIFEST_BYTES:
                    raise CatalogUnavailable("Microsoft catalog package manifest exceeded its size limit")
                manifest_bytes = archive.read("AppxManifest.xml")
                if b"<!DOCTYPE" in manifest_bytes.upper() or b"<!ENTITY" in manifest_bytes.upper():
                    raise CatalogUnavailable("Microsoft catalog package manifest contained prohibited XML declarations")
                root = ET.fromstring(manifest_bytes)
                identity = root.find(".//{*}Identity")
                if identity is None:
                    raise CatalogUnavailable("Microsoft catalog package identity was missing")
                if (
                    identity.attrib.get("Name") != EXPECTED_PACKAGE_NAME
                    or identity.attrib.get("Publisher") != EXPECTED_PUBLISHER
                ):
                    raise CatalogUnavailable("Microsoft catalog package publisher identity did not match")

                db_members = [
                    name
                    for name in names
                    if name.startswith("Public/")
                    and PurePosixPath(name).name.lower() == "index.db"
                ]
                if len(db_members) != 1:
                    raise CatalogUnavailable("Microsoft catalog did not contain exactly one Public/index.db")
                db_info = archive.getinfo(db_members[0])
                if db_info.file_size <= 0 or db_info.file_size > MAX_INDEX_DB_BYTES:
                    raise CatalogUnavailable("Microsoft catalog database size was invalid")
                database_bytes = archive.read(db_members[0])
                if len(database_bytes) != db_info.file_size:
                    raise CatalogUnavailable("Microsoft catalog database size did not match its archive entry")

                connection = sqlite3.connect(":memory:", check_same_thread=False)
                connection.deserialize(database_bytes)
                check = connection.execute("PRAGMA quick_check").fetchone()
                if not check or check[0] != "ok":
                    raise CatalogUnavailable("Microsoft catalog database integrity check failed")
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(packages)").fetchall()
                }
                if not {"id", "name", "moniker", "latest_version"}.issubset(columns):
                    raise CatalogUnavailable("Microsoft catalog database schema was not recognized")
                connection.execute("PRAGMA query_only = ON")

                source_version = identity.attrib.get("Version", "")
                source_version_parts = source_version.split(".")
                if (
                    len(source_version_parts) != 4
                    or len(source_version) > 32
                    or any(
                        not part.isascii() or not part.isdigit() or len(part) > 8
                        for part in source_version_parts
                    )
                ):
                    raise CatalogUnavailable("Microsoft catalog package version was invalid")

            previous = self._connection
            self._connection = connection
            connection = None
            if previous is not None:
                previous.close()
            self._source_version = source_version
            self._source_sha256 = digest.hexdigest()
            self._checked_at = self._utc_clock()
            self._expires_at = self._monotonic() + CACHE_TTL_SECONDS
        except CatalogUnavailable:
            raise
        except (
            OSError,
            ValueError,
            TypeError,
            zipfile.BadZipFile,
            sqlite3.Error,
            ET.ParseError,
            requests.RequestException,
            AttributeError,
        ):
            raise CatalogUnavailable("Microsoft catalog could not be parsed safely") from None
        finally:
            if connection is not None:
                connection.close()
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass


def _validate_query(query: str) -> str:
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    normalized = " ".join(query.split())
    if not QUERY_PATTERN.fullmatch(normalized):
        raise ValueError("query must contain 2 to 128 printable characters")
    return normalized


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()

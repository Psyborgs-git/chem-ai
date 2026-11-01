"""Provider keys live in the user's macOS Keychain, never artifact blobs.

Security.framework is called in-process: no secret is placed in a subprocess
argument, shell command, environment variable, database, or application log.
Other platforms fail explicitly; tests inject an in-memory implementation.
"""

from __future__ import annotations

import ctypes
import platform
import uuid
from functools import lru_cache
from typing import Any, Protocol

from studio.errors import DomainError, ErrorCode

_SERVICE = b"chemistry-studio.inference-provider"


class SecretStore(Protocol):
    def put(self, workspace_id: uuid.UUID, reference: uuid.UUID, secret: str) -> None: ...
    def get(self, workspace_id: uuid.UUID, reference: uuid.UUID) -> str: ...
    def delete(self, workspace_id: uuid.UUID, reference: uuid.UUID) -> None: ...


def _unavailable() -> DomainError:
    return DomainError(
        ErrorCode.CONFLICT,
        "secure API key storage is unavailable or locked; "
        "unlock the macOS login Keychain and retry",
        field_path="apiKey",
    )


class UnavailableSecretStore:
    def put(self, workspace_id: uuid.UUID, reference: uuid.UUID, secret: str) -> None:
        raise _unavailable()

    def get(self, workspace_id: uuid.UUID, reference: uuid.UUID) -> str:
        raise _unavailable()

    def delete(self, workspace_id: uuid.UUID, reference: uuid.UUID) -> None:
        raise _unavailable()


class MacOSKeychain:
    def __init__(self) -> None:
        self._security: Any = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        self._core: Any = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        for name in (
            "SecKeychainAddGenericPassword",
            "SecKeychainFindGenericPassword",
            "SecKeychainItemDelete",
            "SecKeychainItemFreeContent",
        ):
            getattr(self._security, name).restype = ctypes.c_int32
        self._security.SecKeychainAddGenericPassword.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_void_p,
        ]
        self._security.SecKeychainFindGenericPassword.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self._security.SecKeychainItemDelete.argtypes = [ctypes.c_void_p]
        self._security.SecKeychainItemFreeContent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._core.CFRelease.argtypes = [ctypes.c_void_p]
        self._core.CFRelease.restype = None
        self._security.SecKeychainSetUserInteractionAllowed.argtypes = [ctypes.c_bool]
        self._security.SecKeychainSetUserInteractionAllowed.restype = ctypes.c_int32
        # A background API must fail clearly instead of opening an unexpected
        # system permission sheet. The user can unlock Keychain and retry.
        if self._security.SecKeychainSetUserInteractionAllowed(False) != 0:
            raise OSError("Keychain interaction policy unavailable")

    @staticmethod
    def _account(workspace_id: uuid.UUID, reference: uuid.UUID) -> bytes:
        return f"{workspace_id}:{reference}".encode("ascii")

    def put(self, workspace_id: uuid.UUID, reference: uuid.UUID, secret: str) -> None:
        account = self._account(workspace_id, reference)
        data = secret.encode("utf-8")
        status = self._security.SecKeychainAddGenericPassword(
            None, len(_SERVICE), _SERVICE, len(account), account, len(data), data, None
        )
        if status != 0:
            raise _unavailable()

    def get(self, workspace_id: uuid.UUID, reference: uuid.UUID) -> str:
        account = self._account(workspace_id, reference)
        length = ctypes.c_uint32()
        data = ctypes.c_void_p()
        status = self._security.SecKeychainFindGenericPassword(
            None,
            len(_SERVICE),
            _SERVICE,
            len(account),
            account,
            ctypes.byref(length),
            ctypes.byref(data),
            None,
        )
        if status != 0:
            raise _unavailable()
        try:
            return ctypes.string_at(data, length.value).decode("utf-8")
        finally:
            self._security.SecKeychainItemFreeContent(None, data)

    def delete(self, workspace_id: uuid.UUID, reference: uuid.UUID) -> None:
        account = self._account(workspace_id, reference)
        item = ctypes.c_void_p()
        status = self._security.SecKeychainFindGenericPassword(
            None, len(_SERVICE), _SERVICE, len(account), account, None, None, ctypes.byref(item)
        )
        if status == -25300:  # errSecItemNotFound: deletion is idempotent.
            return
        if status != 0:
            raise _unavailable()
        try:
            if self._security.SecKeychainItemDelete(item) != 0:
                raise _unavailable()
        finally:
            self._core.CFRelease(item)


@lru_cache(maxsize=1)
def get_secret_store() -> SecretStore:
    if platform.system() != "Darwin":
        return UnavailableSecretStore()
    try:
        return MacOSKeychain()
    except OSError:
        return UnavailableSecretStore()

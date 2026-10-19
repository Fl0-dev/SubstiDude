# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Écriture locale sûre dans un nouveau PDF ; exécution dans le worker borné."""

import ctypes
from ctypes import wintypes
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4


class ExportError(ValueError):
    pass


def restrict_access(path):
    """DACL protégée : utilisateur courant et SYSTEM, avant tout contenu écrit."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                         wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    advapi.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    token, sid, descriptor = wintypes.HANDLE(), wintypes.LPWSTR(), ctypes.c_void_p()
    try:
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
            raise OSError()
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            raise OSError()
        user_sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        if not advapi.ConvertSidToStringSidW(user_sid, ctypes.byref(sid)):
            raise OSError()
        flags = "OICI" if Path(path).is_dir() else ""
        sddl = f"D:P(A;{flags};FA;;;SY)(A;{flags};FA;;;{sid.value})"
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
            raise OSError()
        if not advapi.SetFileSecurityW(str(path), 0x80000004, descriptor):
            raise OSError()
    finally:
        if descriptor:
            kernel.LocalFree(descriptor)
        if sid:
            kernel.LocalFree(sid)
        if token:
            kernel.CloseHandle(token)


def journal_directory():
    directory = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "SubstiDude" / "temporaries"
    directory.mkdir(parents=True, exist_ok=True)
    restrict_access(directory)
    return directory


def process_running(pid):
    # En cas d'accès refusé, garder l'entrée plutôt que risquer de supprimer un
    # temporaire encore utilisé. Un PID réutilisé peut retarder le nettoyage.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER : PID disparu
    try:
        status = wintypes.DWORD()
        return not kernel.GetExitCodeProcess(handle, ctypes.byref(status)) or status.value == 259
    finally:
        kernel.CloseHandle(handle)


def cleanup_abandoned(directory=None):
    directory = Path(directory) if directory is not None else journal_directory()
    removed = 0
    for record in directory.glob("entry-*.json"):
        try:
            if record.is_symlink() or record.stat().st_size > 32_768:
                continue
            entry = json.loads(record.read_text(encoding="utf-8"))
            path = Path(entry["temporary"])
            if (type(entry["pid"]) is not int or not 0 < entry["pid"] < 2**32
                    or process_running(entry["pid"]) or path.is_symlink()
                    or not re.fullmatch(r"\.substidude-[a-z0-9_]+\.tmp", path.name)):
                continue
            path.unlink(missing_ok=True)
            record.unlink()
            removed += 1
        except (ValueError, KeyError, TypeError):
            # Les nouveaux noms portent le PID : un journal interrompu peut
            # être retiré quand son propriétaire est terminé. Aucun temporaire
            # PDF n'est créé avant le journal complet et fsync.
            match = re.fullmatch(r"entry-(\d+)-[a-z0-9_]+\.json", record.name)
            if match and 0 < int(match[1]) < 2**32 and not process_running(int(match[1])):
                try:
                    record.unlink()
                except OSError:
                    pass
            continue
        except OSError:
            # Ne pas journaliser le contenu ni les chemins ; reprendre plus tard.
            continue
    return removed


def write_export(result, source_path, destination, *, overwrite=False, directory=None):
    """Réouverture d'écriture distincte des contrôles de génération déjà effectués."""
    from substidude.pdf_engine import _open_mupdf, _open_supported_structure
    temporary = record = None
    try:
        source, target = Path(source_path).resolve(), Path(destination).absolute()
        if source == target.resolve() or (target.exists() and os.path.samefile(source, target)):
            raise ExportError("Le chemin source ou un de ses alias ne peut pas être remplacé.")
        if target.exists() and not overwrite:
            raise ExportError("La destination existe ; une confirmation de remplacement est nécessaire.")
        original_stat = target.stat() if target.exists() else None
        directory = Path(directory) if directory is not None else journal_directory()
        directory.mkdir(parents=True, exist_ok=True)
        restrict_access(directory)
        candidate = target.parent / (".substidude-" + uuid4().hex + ".tmp")
        entry_descriptor, entry_name = tempfile.mkstemp(prefix=f"entry-{os.getpid()}-", suffix=".json", dir=directory)
        record = Path(entry_name)
        with os.fdopen(entry_descriptor, "w", encoding="utf-8") as entry:
            restrict_access(record)
            json.dump({"temporary": str(candidate), "pid": os.getpid()}, entry)
            entry.flush()
            os.fsync(entry.fileno())
        descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_BINARY, 0o600)
        temporary = candidate
        # Fermer même si la configuration des droits échoue.
        with os.fdopen(descriptor, "wb") as stream:
            restrict_access(temporary)
            stream.write(result)
            stream.flush()
            os.fsync(stream.fileno())
        written = temporary.read_bytes()
        if sha256(written).digest() != sha256(result).digest() or written != result:
            raise ExportError("Les octets écrits ne correspondent pas au résultat confirmé.")
        with _open_supported_structure(written, allow_missing_self_xref=False), _open_mupdf(written):
            pass
        if overwrite:
            current = target.stat() if target.exists() else None
            if current != original_stat:
                raise ExportError("La destination a changé pendant l'export ; recommencer sa confirmation.")
            os.replace(temporary, target)
        else:
            # Sous Windows rename refuse une destination apparue entre-temps.
            os.rename(temporary, target)
        temporary = None
    except ExportError:
        raise
    except Exception:
        raise ExportError("L'export a échoué ; aucune destination partielle n'est validée.") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                # Garder le journal si le nettoyage doit être repris au démarrage.
                record = None
        if record is not None:
            try:
                record.unlink(missing_ok=True)
            except OSError:
                pass

# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Limite native du processus PDF, sans dépendance ni prétention de sandbox."""

import ctypes
from ctypes import wintypes


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class IOCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IOCounters)] + [
        (name, ctypes.c_size_t) for name in (
            "ProcessMemoryLimit", "JobMemoryLimit", "PeakProcessMemoryUsed", "PeakJobMemoryUsed",
        )
    ]


class WindowsMemoryBudget:
    """Job Object anonyme, attaché avant import/ouverture des moteurs PDF."""

    def __init__(self, limit):
        self.limit = limit
        self.handle = None
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
        ]
        self.kernel.QueryInformationJobObject.restype = wintypes.BOOL
        self.kernel.GetCurrentProcess.restype = wintypes.HANDLE
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL

    def __enter__(self):
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            limits = ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
            limits.ProcessMemoryLimit = self.limit
            if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.kernel.AssignProcessToJobObject(self.handle, self.kernel.GetCurrentProcess()):
                raise ctypes.WinError(ctypes.get_last_error())
            actual = ExtendedLimits()
            if not self.kernel.QueryInformationJobObject(self.handle, 9, ctypes.byref(actual), ctypes.sizeof(actual), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if actual.ProcessMemoryLimit != self.limit or not actual.BasicLimitInformation.LimitFlags & 0x100:
                raise OSError("La limite mémoire Windows n'est pas vérifiée.")
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *ignored):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
        # Pas de KILL_ON_JOB_CLOSE : l'enfant doit pouvoir terminer normalement.
        # L'association au job reste effective jusqu'à la sortie du processus.

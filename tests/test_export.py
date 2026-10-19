# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

from pathlib import Path
import json
import os
import ctypes
from ctypes import wintypes
import tempfile
import unittest
from unittest.mock import patch

from fixtures import TARGET_RECT, make_pdf
from substidude.export import ExportError, cleanup_abandoned, write_export
from substidude.model import Session, SessionError, Substitution
from substidude.pipeline import transform


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="substidude-export-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source, self.destination, self.journal = self.root / "synthetic.pdf", self.root / "copy.pdf", self.root / "journal"
        self.original = make_pdf()
        self.source.write_bytes(self.original)
        self.result = transform(self.original, [Substitution(0, TARGET_RECT, "Toto")])

    def export(self, **options):
        write_export(self.result, self.source, self.destination, directory=self.journal, **options)

    def test_exact_bytes_and_no_source_mutation_or_remaining_temp(self):
        self.export()
        self.assertEqual(self.result, self.destination.read_bytes())
        self.assertEqual(self.original, self.source.read_bytes())
        self.assertEqual([], list(self.journal.iterdir()))
        self.assertEqual([], list(self.root.glob(".substidude-*.tmp")))

    def test_source_alias_and_existing_destination_require_refusal_or_confirmation(self):
        with self.assertRaises(ExportError):
            write_export(self.result, self.source, self.source, overwrite=True, directory=self.journal)
        os.link(self.source, self.destination)
        with self.assertRaises(ExportError):
            self.export(overwrite=True)
        self.destination.unlink()
        self.destination.write_bytes(b"previous-destination")
        with self.assertRaises(ExportError):
            self.export()
        self.assertEqual(b"previous-destination", self.destination.read_bytes())
        self.export(overwrite=True)
        self.assertEqual(self.result, self.destination.read_bytes())

    def test_finalize_failure_preserves_existing_destination_and_cleans(self):
        self.destination.write_bytes(b"previous-destination")
        with patch("substidude.export.os.replace", side_effect=PermissionError("synthetic")):
            with self.assertRaises(ExportError):
                self.export(overwrite=True)
        self.assertEqual(b"previous-destination", self.destination.read_bytes())
        self.assertEqual(self.original, self.source.read_bytes())
        self.assertEqual([], list(self.journal.iterdir()))
        self.assertEqual([], list(self.root.glob(".substidude-*.tmp")))

    def test_invalid_written_pdf_and_permission_failure_never_publish(self):
        for data in (b"invalid", b""):
            with self.subTest(data=data), self.assertRaises(ExportError):
                write_export(data, self.source, self.destination, directory=self.journal)
            self.assertFalse(self.destination.exists())
        with patch("substidude.export.restrict_access", side_effect=PermissionError("synthetic")):
            with self.assertRaises(ExportError):
                self.export()
        self.assertFalse(self.destination.exists())

    def test_abandoned_only_registered_temp_of_dead_session_is_removed(self):
        self.journal.mkdir()
        abandoned = self.root / ".substidude-synthetic.tmp"
        abandoned.write_bytes(b"synthetic")
        record = self.journal / "entry-synthetic.json"
        record.write_text(json.dumps({"temporary": str(abandoned), "pid": os.getpid()}), encoding="utf-8")
        self.assertEqual(0, cleanup_abandoned(self.journal))
        self.assertTrue(abandoned.exists())
        with patch("substidude.export.process_running", return_value=False):
            self.assertEqual(1, cleanup_abandoned(self.journal))
        self.assertFalse(abandoned.exists())
        self.assertFalse(record.exists())
        unrelated = self.root / "other.tmp"
        unrelated.write_bytes(b"synthetic")
        record.write_text(json.dumps({"temporary": str(unrelated), "pid": 123}), encoding="utf-8")
        with patch("substidude.export.process_running", return_value=False):
            self.assertEqual(0, cleanup_abandoned(self.journal))
        self.assertTrue(unrelated.exists())

    def test_exported_state_requires_the_exact_confirmed_revision(self):
        session = Session(self.original)
        session.set_substitutions([Substitution(0, TARGET_RECT, "Toto")])
        ticket = session.begin_generation()
        session.accept_result(ticket, self.result)
        with self.assertRaises(SessionError):
            session.mark_exported(self.result)
        session.confirm()
        session.mark_exported(self.result)
        self.assertEqual("Exporté", session.state)
        session.set_substitutions([])
        self.assertEqual("À vérifier", session.state)

    def test_flush_failure_and_real_locked_destination_preserve_old_file(self):
        self.destination.write_bytes(b"previous-destination")
        with patch("substidude.export.os.fsync", side_effect=OSError("synthetic disk full")):
            with self.assertRaises(ExportError):
                self.export(overwrite=True)
        self.assertEqual(b"previous-destination", self.destination.read_bytes())
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(self.destination), 0x80000000, 0, None, 3, 0, None)
        self.assertNotEqual(ctypes.c_void_p(-1).value, handle)
        try:
            with self.assertRaises(ExportError):
                self.export(overwrite=True)
        finally:
            kernel.CloseHandle(handle)
        self.assertEqual(b"previous-destination", self.destination.read_bytes())
        self.assertEqual(self.original, self.source.read_bytes())
        self.assertEqual([], list(self.root.glob(".substidude-*.tmp")))

    def test_destination_changed_during_export_requires_fresh_confirmation(self):
        self.destination.write_bytes(b"previous-destination")
        sync = os.fsync
        def change_destination(fd):
            sync(fd)
            self.destination.write_bytes(b"changed-by-another-operation")
        with patch("substidude.export.os.fsync", change_destination):
            with self.assertRaises(ExportError):
                self.export(overwrite=True)
        self.assertEqual(b"changed-by-another-operation", self.destination.read_bytes())
        self.assertEqual([], list(self.root.glob(".substidude-*.tmp")))

    def test_journal_is_durable_before_the_pdf_temporary_is_created(self):
        sync, calls = os.fsync, []
        def check_order(fd):
            if not calls:
                self.assertEqual([], list(self.root.glob(".substidude-*.tmp")))
            calls.append(fd)
            sync(fd)
        with patch("substidude.export.os.fsync", check_order):
            self.export()
        self.assertEqual(2, len(calls))

    def test_incomplete_journal_is_removed_only_after_its_owner_exits(self):
        self.journal.mkdir()
        record = self.journal / f"entry-{os.getpid()}-synthetic.json"
        record.write_text('{"temporary":', encoding="utf-8")
        cleanup_abandoned(self.journal)
        self.assertTrue(record.exists())
        with patch("substidude.export.process_running", return_value=False):
            cleanup_abandoned(self.journal)
        self.assertFalse(record.exists())


if __name__ == "__main__":
    unittest.main()

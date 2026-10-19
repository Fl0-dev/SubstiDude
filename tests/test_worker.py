# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

from io import BytesIO
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

import pymupdf
from PIL import Image

from fixtures import TARGET_RECT, make_pdf
from substidude.model import Session, Substitution
from substidude.worker import PDFJob, WorkerError, SessionController, UncertainExportError
from unittest.mock import patch
from substidude import worker


class WorkerTests(unittest.TestCase):
    def test_transform_four_modes_render_inspect_and_open(self):
        job = PDFJob()
        self.addCleanup(job.cancel)
        for kind in ("native", "scan", "ocr", "mixed"):
            with self.subTest(kind=kind):
                source = make_pdf(kind)
                rect = tuple(pymupdf.Rect(TARGET_RECT) + ((0, 200, 0, 200) if kind == "mixed" else (0, 0, 0, 0)))
                job.start("transform", source, substitutions=[Substitution(0, rect, "Élodie")])
                result = job.receive()
                self.assertTrue(result.startswith(b"%PDF-"))
                job.start("inspect", result)
                info = json.loads(job.receive())
                self.assertEqual(1, len(info["pages"]))
                self.assertTrue(info["warnings"])
                job.start("render", result, page=0, scale=1)
                rendered = job.receive()
                width, height = struct.unpack_from(">II", rendered)
                self.assertEqual(8 + width * height * 3, len(rendered))
        with tempfile.TemporaryDirectory(prefix="substidude-worker-") as directory:
            path = Path(directory) / "synthetic.pdf"
            source = make_pdf()
            path.write_bytes(source)
            job.start("open", path=str(path))
            self.assertEqual(source, job.receive())
            self.assertEqual(source, path.read_bytes())

    def test_session_controller_invalidates_stale_result_and_confirmation(self):
        session = Session(make_pdf("ocr"))
        session.set_substitutions([Substitution(0, TARGET_RECT, "Toto")])
        controller = SessionController(session)
        self.addCleanup(controller.close)
        controller.generate()
        with self.assertRaises(WorkerError):
            controller.generate()
        session.set_substitutions([Substitution(0, TARGET_RECT, "John Doe")])
        self.assertFalse(controller.collect())
        self.assertIsNone(session.result)
        controller.generate()
        self.assertTrue(controller.collect())
        session.confirm()
        self.assertIs(session.result, session.confirmed_bytes())
        controller.generate()
        controller.cancel()
        self.assertIsNone(session.result)

    def test_invalid_command_budgets_rejection_overflow_and_restart(self):
        for kwargs in ({"duration": 61}, {"memory_limit": 2**31 + 1}, {"response_limit": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(WorkerError):
                PDFJob(**kwargs)
        job = PDFJob(response_limit=1024)
        self.addCleanup(job.cancel)
        with self.assertRaises(WorkerError):
            job.start("not-a-command", b"synthetic")
        job.start("transform", make_pdf(), substitutions=[Substitution(0, TARGET_RECT, "Toto")])
        with self.assertRaisesRegex(WorkerError, "IPC"):
            job.receive()
        job.start("inspect", make_pdf(encrypted=True))
        with self.assertRaisesRegex(WorkerError, "refusé") as caught:
            job.receive()
        self.assertNotIn("SECRET", str(caught.exception))
        job.start("inspect", make_pdf())
        self.assertEqual(1, len(json.loads(job.receive())["pages"]))

    def test_deadline_without_collect_and_parent_has_no_pdf_dependencies(self):
        job = PDFJob(duration=0.001)
        self.addCleanup(job.cancel)
        job.start("inspect", make_pdf())
        job.process.join(5)
        self.assertFalse(job.process.is_alive())
        with self.assertRaisesRegex(WorkerError, "délai"):
            job.receive()
        check = subprocess.run([sys.executable, "-B", "-W", "error", "-c",
            "import sys; import substidude.worker; "
            "assert not any(x in sys.modules for x in ('pymupdf', 'pikepdf', 'PIL', 'pypdfium2')); print('ok')"],
            capture_output=True, timeout=15)
        self.assertEqual(0, check.returncode)
        self.assertEqual(b"ok", check.stdout.strip())

    def test_clean_parent_end_to_end_without_test_dependencies(self):
        with tempfile.TemporaryDirectory(prefix="substidude-worker-") as directory:
            for kind in ("native", "scan", "ocr", "mixed"):
                (Path(directory) / (kind + ".pdf")).write_bytes(make_pdf(kind))
            check = subprocess.run([sys.executable, "-B", "-W", "error",
                str(Path(__file__).with_name("application_probe.py")), "--directory", directory],
                capture_output=True, timeout=60)
            self.assertEqual(0, check.returncode, check.stderr.decode(errors="replace"))
            report = json.loads(check.stdout)
            self.assertEqual(4, len(report["checks"]))
            self.assertTrue(report["parent_without_pdf_engines"])

    def test_native_setup_failure_never_executes_pdf_and_start_failure_cleans_up(self):
        from unittest.mock import MagicMock
        sender = MagicMock()
        with patch("substidude.windows_memory.WindowsMemoryBudget", side_effect=OSError("synthetic")), \
                patch.object(worker, "_execute") as execute:
            worker._child(sender, "inspect", b"", b"{}", 0, b"X" * 16, 1024, 1024)
        execute.assert_not_called()
        status, _, _, _ = worker.HEADER.unpack_from(sender.send_bytes.call_args.args[0])
        self.assertEqual(5, status)
        sender.close.assert_called_once()
        job = PDFJob()
        with patch("multiprocessing.context.SpawnProcess.start", side_effect=OSError("synthetic")):
            with self.assertRaises(WorkerError):
                job.start("inspect", make_pdf())
        self.assertIsNone(job.process)
        self.assertIsNone(job.receiver)

    def test_reply_revision_or_request_tampering_is_rejected(self):
        job = PDFJob()
        self.addCleanup(job.cancel)
        for attribute, value in (("revision", 999), ("request_id", b"X" * 16)):
            job.start("inspect", make_pdf())
            setattr(job, attribute, value)
            with self.assertRaisesRegex(WorkerError, "périmé"):
                job.receive()

    def test_worker_exports_only_supplied_result_and_preserves_source(self):
        with tempfile.TemporaryDirectory(prefix="substidude-worker-") as directory, PDFJob() as job:
            path = Path(directory) / "synthetic.pdf"
            destination = Path(directory) / "copy.pdf"
            source = make_pdf("ocr")
            path.write_bytes(source)
            job.start("transform", source, substitutions=[Substitution(0, TARGET_RECT, "Toto")])
            result = job.receive()
            job.start("export", result, path=str(destination), source_path=str(path))
            self.assertEqual(b"exported", job.receive())
            self.assertEqual(result, destination.read_bytes())
            self.assertEqual(source, path.read_bytes())
            job.start("export", result, path=str(path), source_path=str(path), overwrite=True)
            with self.assertRaises(WorkerError):
                job.receive()
            self.assertEqual(source, path.read_bytes())

    def test_export_ack_budget_is_checked_before_any_file_publication(self):
        with PDFJob(response_limit=worker.HEADER.size) as job:
            with self.assertRaises(WorkerError):
                job.start("export", make_pdf(), path="synthetic-copy.pdf", source_path="synthetic.pdf", overwrite=True)

    def test_untrusted_ack_after_finalization_is_uncertain_not_false_failure(self):
        with tempfile.TemporaryDirectory(prefix="substidude-worker-") as directory, PDFJob() as job:
            path, target = Path(directory) / "synthetic.pdf", Path(directory) / "copy.pdf"
            source = make_pdf()
            path.write_bytes(source)
            target.write_bytes(b"previous-destination")
            job.start("transform", source, substitutions=[Substitution(0, TARGET_RECT, "Toto")])
            result = job.receive()
            job.start("export", result, path=str(target), source_path=str(path), overwrite=True)
            job.process.join(15)
            self.assertFalse(job.process.is_alive())
            job.request_id = b"X" * 16  # Simuler un accusé non authentifiable.
            with self.assertRaises(UncertainExportError):
                job.receive()
            self.assertEqual(result, target.read_bytes())
            self.assertEqual(source, path.read_bytes())


if __name__ == "__main__":
    unittest.main()

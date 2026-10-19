# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Tests du banc spawn, hors de l'application et sans nouveau plafond produit."""

import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from windows_probe import ProbeError, ProbeJob


class WindowsProbeTests(unittest.TestCase):
    def test_source_self_check_in_a_clean_parent(self):
        # Le lanceur unittest a déjà importé les moteurs ; le parent propre est
        # donc un sous-processus de recette, comme le futur exécutable onedir.
        completed = subprocess.run(
            [sys.executable, "-B", "-W", "error", str(Path(__file__).with_name("windows_probe.py")),
             "--self-test"], capture_output=True, check=True, timeout=90,
        )
        report = json.loads(completed.stdout)
        self.assertFalse(report["application"])
        self.assertFalse(report["frozen"])
        self.assertEqual("spawn", report["start_method"])
        self.assertEqual(15, len(report["checks"]))
        self.assertEqual(b"", completed.stderr)

    def test_invalid_command_and_empty_receive_are_neutral(self):
        job = ProbeJob()
        for mode, revision in (("unknown", 1), ("native", "SECRET-CIBLE-123")):
            with self.assertRaises(ProbeError) as caught:
                job.start(mode, revision)
            self.assertNotIn("SECRET", str(caught.exception))
            self.assertIsNone(job.process)
        with self.assertRaises(ProbeError):
            job.receive(1, watchdog=0)
        job.cancel()

    def test_start_failure_releases_the_pipe(self):
        job = ProbeJob()
        with patch("multiprocessing.process.BaseProcess.start", side_effect=OSError("SECRET-CIBLE-123")):
            with self.assertRaises(ProbeError) as caught:
                job.start()
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertIsNone(job.process)
        self.assertIsNone(job.receiver)


if __name__ == "__main__":
    unittest.main()

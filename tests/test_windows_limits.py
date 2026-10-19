# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Dépassements réels avec budgets réduits, sans gros document ni forte allocation."""

import time
import unittest
from unittest.mock import MagicMock, patch

from windows_probe import ProbeError, ProbeJob
from windows_memory import WindowsMemoryBudget


class WindowsLimitTests(unittest.TestCase):
    def test_invalid_budgets_are_refused(self):
        for budget in ({"memory_limit": 0}, {"memory_limit": 2**31 + 1},
                       {"response_limit": 12}, {"response_limit": 64 * 1024 * 1024 + 1},
                       {"duration": 61}, {"duration": float("nan")}):
            with self.subTest(budget=budget), self.assertRaises(ProbeError):
                ProbeJob(**budget)

    def test_job_setup_failure_closes_handle_without_fallback(self):
        kernel = MagicMock()
        kernel.CreateJobObjectW.return_value = 123
        kernel.SetInformationJobObject.return_value = False
        with patch("windows_memory.ctypes.WinDLL", return_value=kernel):
            with self.assertRaises(OSError):
                with WindowsMemoryBudget(64 * 1024 * 1024):
                    self.fail("Le traitement ne doit pas démarrer sans limite native.")
        kernel.CloseHandle.assert_called_once_with(123)
        kernel.AssignProcessToJobObject.assert_not_called()

    def test_native_memory_budget_denies_allocation(self):
        job = ProbeJob(memory_limit=64 * 1024 * 1024)
        try:
            job.start("memory")
            with self.assertRaisesRegex(ProbeError, "mémoire"):
                job.receive(1, watchdog=15)
            self.assertIsNone(job.process)
        finally:
            job.cancel()

    def test_encoded_ipc_boundary_and_sender_overflow(self):
        job = ProbeJob(response_limit=1024)
        try:
            job.start("reply-boundary")
            result = job.receive(1, watchdog=15)
            self.assertEqual(1024 - 13, len(result))
            job.start("reply-overflow")
            with self.assertRaisesRegex(ProbeError, "IPC"):
                job.receive(1, watchdog=15)
            self.assertIsNone(job.process)
        finally:
            job.cancel()

    def test_receiver_refuses_oversized_wire_message(self):
        job = ProbeJob(response_limit=1024)
        try:
            job.start("wire-overflow")
            with self.assertRaisesRegex(ProbeError, "IPC"):
                job.receive(1, watchdog=15)
            self.assertIsNone(job.reader)
        finally:
            job.cancel()

    def test_deadline_includes_time_before_receive(self):
        job = ProbeJob()
        try:
            job.start("wait")
            self.assertTrue(job.ready.wait(15))
            job.started -= 61  # Échéance déjà passée, sans attendre réellement 60 s.
            start = time.monotonic()
            with self.assertRaisesRegex(ProbeError, "surveillance"):
                job.receive(1, watchdog=15)
            self.assertLess(time.monotonic() - start, 5)
            self.assertIsNone(job.reader)
        finally:
            job.cancel()

    def test_deadline_also_stops_a_child_after_complete_reply(self):
        job = ProbeJob(duration=1)
        try:
            job.start("reply-then-wait")
            with self.assertRaisesRegex(ProbeError, "surveillance"):
                job.receive(1, watchdog=15)
            self.assertIsNone(job.process)
            self.assertIsNone(job.reader)
        finally:
            job.cancel()

    def test_deadline_stops_child_even_without_receive(self):
        job = ProbeJob(duration=0.2)
        try:
            job.start("wait")
            job.process.join(timeout=5)
            self.assertFalse(job.process.is_alive())
            self.assertTrue(job.expired.is_set())
            with self.assertRaisesRegex(ProbeError, "surveillance"):
                job.receive(1, watchdog=15)
        finally:
            job.cancel()

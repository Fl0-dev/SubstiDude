# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Qualification Windows/spawn/onedir sur fixtures fixes, pas un worker applicatif.

Aucun chemin PDF utilisateur, interface ni export. Budgets choisis appliqués au banc.
Le parent n'importe pas les moteurs PDF ; chaque enfant possède et ferme ses objets.
"""

import argparse
from hashlib import sha256
from importlib.util import find_spec
import json
import multiprocessing
from math import isfinite
import os
from pathlib import Path
from queue import Empty, Queue
import struct
import sys
from threading import Event, Thread, Timer
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from substidude.limits import MAX_IPC_BYTES, MAX_JOB_SECONDS, MAX_PDF_PROCESS_BYTES


HEADER = struct.Struct(">BqI")  # statut, révision signée 64 bits, PID ; 13 octets.


def _send_reply(sender, status, revision, payload, limit):
    if HEADER.size + len(payload) > limit:
        status, payload = 4, b""
    try:
        sender.send_bytes(HEADER.pack(status, revision, os.getpid()) + payload)
    except (OSError, EOFError, MemoryError):
        # Le parent peut avoir annulé ; aucun diagnostic documentaire à afficher.
        pass


def _read_reply(receiver, replies, limit):
    # Ce thread ne manipule jamais d'objet PDF. Il permet au parent de borner
    # toute l'attente IPC, pas seulement la disponibilité du premier octet.
    try:
        replies.put(("data", receiver.recv_bytes(maxlength=limit)))
    except EOFError:
        replies.put(("closed", None))
    except Exception:
        replies.put(("ipc", None))


def _expire(process, expired):
    expired.set()
    try:
        if process.is_alive():
            process.terminate()
    except (OSError, ValueError):
        pass


class ProbeError(ValueError):
    """Diagnostic neutre du banc de qualification, sans détail documentaire."""


def native_experiment():
    # Réutilise l'expérience native existante, pas le parcours de développement
    # complet qui importerait PDFium dans le paquet de qualification runtime.
    import pymupdf
    from PIL import Image, ImageChops
    from fixtures import KEPT, TARGET, TARGET_RECT
    from substidude.pdf_engine import _open_mupdf, _open_supported_structure, classify_zone, render_page, sanitize_pdf
    from test_engine import NativeExperimentTests

    source, transformed, before, region = NativeExperimentTests.replace_native(rotation=90, cropped=True)
    original_digest = sha256(source).digest()
    rect = pymupdf.Rect(TARGET_RECT) + (-10, -20, -10, -20)
    if classify_zone(source, 0, rect) != "native":
        raise ProbeError("Classification de la fixture non vérifiée.")
    result = sanitize_pdf(transformed)
    with _open_supported_structure(result) as structure, _open_mupdf(result) as document:
        page = document[0]
        text = page.get_text()
        if (structure.check_pdf_syntax() or TARGET in text or KEPT not in text
                or "Société Élodie" not in text or page.rotation != 90):
            raise ProbeError("Résultat de la fixture non vérifié.")
        after = render_page(page)
        original_image = Image.frombytes("RGB", (before.width, before.height), before.samples)
        final_image = Image.frombytes("RGB", (after.width, after.height), after.samples)
        difference = ImageChops.difference(original_image, final_image)
        if difference.getbbox() is None:
            raise ProbeError("Transformation de la fixture absente.")
        box = region.irect
        difference.paste((0, 0, 0), (box.x0, box.y0, box.x1, box.y1))
        if difference.getbbox() is not None:
            raise ProbeError("Rendu hors zone de la fixture modifié.")
    if sha256(source).digest() != original_digest:
        raise ProbeError("La fixture source a changé.")
    return result


def _child(sender, ready, revision, mode, memory_limit, response_limit):
    try:
        from windows_memory import WindowsMemoryBudget

        with WindowsMemoryBudget(memory_limit):
            ready.set()
            if mode == "wait":
                multiprocessing.Event().wait()
            elif mode == "crash":
                os._exit(7)
            elif mode == "error":
                raise RuntimeError("SECRET-CIBLE-123")
            elif mode == "memory":
                allocation = bytearray(memory_limit)  # En plus du processus déjà vivant.
                _send_reply(sender, 0, revision, b"unexpected-memory-success", response_limit)
                return
            elif mode in {"reply-boundary", "reply-overflow"}:
                size = response_limit - HEADER.size + (mode == "reply-overflow")
                _send_reply(sender, 0, revision, b"X" * size, response_limit)
                return
            elif mode == "wire-overflow":
                # Contamination volontaire de transport, avant décodage de l'enveloppe.
                sender.send_bytes(b"X" * (response_limit + 1))
                return
            elif mode == "reply-then-wait":
                _send_reply(sender, 0, revision, b"X", response_limit)
                multiprocessing.Event().wait()
            elif mode == "reject":
                from fixtures import make_pdf
                from substidude.pdf_engine import PDFError, _open_supported_structure
                try:
                    with _open_supported_structure(make_pdf(encrypted=True)):
                        pass
                except PDFError:
                    _send_reply(sender, 2, revision, b"", response_limit)
                else:
                    _send_reply(sender, 0, revision, b"%PDF-incorrectly-accepted", response_limit)
                return
            else:
                result = native_experiment()
                _send_reply(sender, 0, revision, result, response_limit)
                return
    except MemoryError:
        _send_reply(sender, 3, revision, b"", response_limit)
    except Exception:
        # Ne jamais transmettre traceback, chemins, exceptions natives ni contenu.
        _send_reply(sender, 1, revision, b"", response_limit)
    finally:
        sender.close()


class ProbeJob:
    """Un processus et une réponse au maximum ; aucune file de travaux en attente."""

    def __init__(self, *, memory_limit=MAX_PDF_PROCESS_BYTES, duration=MAX_JOB_SECONDS,
                 response_limit=MAX_IPC_BYTES):
        if (type(memory_limit) is not int or not 0 < memory_limit <= MAX_PDF_PROCESS_BYTES
                or type(response_limit) is not int or not HEADER.size <= response_limit <= MAX_IPC_BYTES
                or type(duration) not in (int, float) or not isfinite(duration)
                or not 0 < duration <= MAX_JOB_SECONDS):
            raise ProbeError("Budget d'essai invalide.")
        self.memory_limit, self.duration, self.response_limit = memory_limit, duration, response_limit
        self.context = multiprocessing.get_context("spawn")
        self.process = None
        self.receiver = None
        self.ready = None
        self.reader = None
        self.replies = None
        self.started = None
        self.timer = None
        self.expired = None

    def start(self, mode="native", revision=1):
        if self.process is not None:
            raise ProbeError("Un traitement d'essai est déjà actif ou non collecté.")
        if (mode not in {"native", "reject", "error", "wait", "crash", "memory", "reply-boundary",
                         "reply-overflow", "wire-overflow", "reply-then-wait"}
                or type(revision) is not int or not -(2**63) <= revision < 2**63):
            raise ProbeError("Commande d'essai invalide.")
        self.receiver, sender = self.context.Pipe(duplex=False)
        self.ready = self.context.Event()
        self.process = self.context.Process(target=_child, args=(
            sender, self.ready, revision, mode, self.memory_limit, self.response_limit,
        ))
        try:
            self.started = monotonic()
            self.process.start()
            self.expired = Event()
            self.timer = Timer(max(0, self.duration - (monotonic() - self.started)),
                               _expire, args=(self.process, self.expired))
            self.timer.daemon = True
            self.timer.start()
            self.replies = Queue(maxsize=1)
            self.reader = Thread(target=_read_reply, args=(self.receiver, self.replies, self.response_limit),
                                 name="SubstiDudeProbeIPC", daemon=True)
            self.reader.start()
        except Exception:
            self.cancel()
            raise ProbeError("Le processus d'essai n'a pas pu démarrer.") from None
        finally:
            sender.close()

    def cancel(self):
        if self.process is not None:
            if self.timer is not None:
                self.timer.cancel()
                if self.timer.ident is not None:
                    self.timer.join()
            if self.process.pid is not None:
                if self.process.is_alive():
                    self.process.terminate()
                self.process.join()
            self.process.close()
            self.receiver.close()
            if self.reader is not None and self.reader.ident is not None:
                self.reader.join()
            self.process = self.receiver = self.ready = None
            self.reader = self.replies = self.started = None
            self.timer = self.expired = None

    def receive(self, revision, watchdog=None):
        """Échéance globale depuis start ; watchdog optionnel plus court pour les tests."""
        if self.process is None:
            raise ProbeError("Aucun traitement d'essai actif.")
        try:
            remaining = self.duration - (monotonic() - self.started)
            if watchdog is not None:
                if type(watchdog) not in (int, float) or not isfinite(watchdog) or watchdog < 0:
                    raise ProbeError("Délai de surveillance invalide.")
                remaining = min(remaining, watchdog)
            if remaining <= 0:
                raise ProbeError("Le délai de surveillance du test est dépassé.")
            kind, packet = self.replies.get(timeout=remaining)
            if self.expired.is_set():
                raise ProbeError("Le délai de surveillance du test est dépassé.")
            if kind == "closed":
                raise ProbeError("Le processus d'essai s'est arrêté sans résultat.")
            if kind != "data" or len(packet) < HEADER.size:
                raise ProbeError("La réponse IPC d'essai est invalide ou trop grande.")
            status, received_revision, child_pid = HEADER.unpack_from(packet)
            remaining = self.duration - (monotonic() - self.started)
            if remaining <= 0:
                raise ProbeError("Le délai de surveillance du test est dépassé.")
            # Réponse reçue AVANT join ; fermeture normale également bornée par l'échéance.
            self.process.join(timeout=remaining)
            if (self.process.is_alive() or self.expired.is_set()
                    or monotonic() - self.started >= self.duration):
                raise ProbeError("Le délai de surveillance du test est dépassé.")
            if received_revision != revision:
                raise ProbeError("Résultat d'essai périmé.")
            if status == 2:
                raise ProbeError("Le PDF d'essai est refusé.")
            if status == 3:
                raise ProbeError("Le budget mémoire du traitement d'essai est dépassé.")
            if status == 4:
                raise ProbeError("La réponse IPC d'essai dépasse le budget.")
            if status != 0:
                raise ProbeError("Le traitement d'essai a échoué.")
            if child_pid != self.process.pid or child_pid == os.getpid():
                raise ProbeError("Le résultat d'essai est invalide.")
            result = packet[HEADER.size:]
            if self.expired.is_set() or monotonic() - self.started >= self.duration:
                raise ProbeError("Le délai de surveillance du test est dépassé.")
            return result
        except Empty:
            raise ProbeError("Le délai de surveillance du test est dépassé.") from None
        except (EOFError, OSError):
            raise ProbeError("Le processus d'essai s'est arrêté sans résultat.") from None
        finally:
            self.cancel()


def self_check():
    """Recette fixe également exécutée dans le binaire gelé, sans PDF persistant."""
    checks = []
    job = ProbeJob()
    try:
        job.start()
        try:
            job.start()
        except ProbeError:
            checks.append("single-active-job")
        else:
            raise AssertionError("Un second travail a été accepté.")
        result = job.receive(1, watchdog=15)
        if not result.startswith(b"%PDF-") or len(result) < 65_536:
            raise AssertionError("La réponse de la fixture est incomplète.")
        checks.append("native-open-render-transform-large-ipc")
        for mode in ("reject", "error", "crash"):
            job.start(mode)
            try:
                job.receive(1, watchdog=15)
            except ProbeError as error:
                if "SECRET" in str(error):
                    raise AssertionError("Un diagnostic expose le contenu.")
                if mode == "reject" and "refusé" not in str(error):
                    raise
                if mode == "crash" and "sans résultat" not in str(error):
                    raise
                checks.append(mode)
            else:
                raise AssertionError("Le scénario d'échec a retourné un résultat.")
        job.start(revision=1)
        try:
            job.receive(2, watchdog=15)
        except ProbeError as error:
            if "périmé" not in str(error):
                raise
            checks.append("stale-result")
        else:
            raise AssertionError("Un résultat périmé a été accepté.")
        for action in ("cancel", "watchdog"):
            job.start("wait")
            if not job.ready.wait(15):
                raise AssertionError("L'enfant d'essai n'a pas démarré.")
            process = job.process
            if action == "cancel":
                job.cancel()
            else:
                try:
                    job.receive(1, watchdog=0)
                except ProbeError as error:
                    if "surveillance" not in str(error):
                        raise
                else:
                    raise AssertionError("L'attente excessive n'a pas été arrêtée.")
            if job.process is not None or not process._closed:
                raise AssertionError("Le processus d'essai n'a pas été libéré.")
            checks.append(action)
        job.start()
        job.receive(1, watchdog=15)
        checks.append("restart-after-stop")
    finally:
        job.cancel()
    pressure = ProbeJob(memory_limit=64 * 1024 * 1024)
    try:
        pressure.start("memory")
        try:
            pressure.receive(1, watchdog=15)
        except ProbeError as error:
            if "mémoire" not in str(error):
                raise
            checks.append("native-memory-budget")
        else:
            raise AssertionError("Le budget mémoire réduit n'a pas bloqué l'allocation.")
    finally:
        pressure.cancel()
    small = ProbeJob(response_limit=1024)
    try:
        small.start("reply-boundary")
        if len(small.receive(1, watchdog=15)) != 1024 - HEADER.size:
            raise AssertionError("La limite IPC exacte n'est pas vérifiée.")
        checks.append("ipc-boundary")
        for mode in ("reply-overflow", "wire-overflow"):
            small.start(mode)
            try:
                small.receive(1, watchdog=15)
            except ProbeError as error:
                if "IPC" not in str(error):
                    raise
                checks.append(mode)
            else:
                raise AssertionError("Une réponse IPC trop grande a été acceptée.")
    finally:
        small.cancel()
    deadline = ProbeJob(duration=1)
    try:
        deadline.start("reply-then-wait")
        try:
            deadline.receive(1, watchdog=15)
        except ProbeError as error:
            if "surveillance" not in str(error):
                raise
            checks.append("deadline-after-reply")
        else:
            raise AssertionError("Un enfant tardif après réponse n'a pas été arrêté.")
    finally:
        deadline.cancel()
    automatic = ProbeJob(duration=0.2)
    try:
        automatic.start("wait")
        automatic.process.join(timeout=5)
        if automatic.process.is_alive() or not automatic.expired.is_set():
            raise AssertionError("L'échéance sans collecte n'a pas arrêté l'enfant.")
        checks.append("deadline-without-receive")
    finally:
        automatic.cancel()
    if "pymupdf" in sys.modules or "pikepdf" in sys.modules:
        raise AssertionError("Le parent a importé un moteur PDF.")
    pdfium = find_spec("pypdfium2") is not None
    if getattr(sys, "frozen", False) and pdfium:
        raise AssertionError("PDFium ne doit pas être embarqué.")
    return {"checks": checks, "frozen": bool(getattr(sys, "frozen", False)),
            "start_method": "spawn", "pdfium_available": pdfium, "application": False,
            "budgets": {"process_bytes": MAX_PDF_PROCESS_BYTES, "job_seconds": MAX_JOB_SECONDS,
                        "response_bytes": MAX_IPC_BYTES}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(self_check()))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()

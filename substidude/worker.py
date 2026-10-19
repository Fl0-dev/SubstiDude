# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Un travail PDF spawn actif, borné, sans moteur PDF importé dans le parent.

Appeler start/receive/cancel depuis un seul propriétaire. receive est bloquant :
la future interface attendra done avant collecte, sans appeler de moteur dans Qt.
Le processus est une isolation de travail, pas un bac à sable de sécurité.
"""

import json
from math import isfinite
import multiprocessing
import os
from queue import Empty, Queue
import struct
from threading import Event, Thread, Timer
from time import monotonic
from uuid import uuid4

from substidude.limits import MAX_IPC_BYTES, MAX_JOB_SECONDS, MAX_PDF_PROCESS_BYTES
from substidude.model import SessionError, Substitution, validate_substitutions

HEADER = struct.Struct(">BqI16s")  # statut, révision, PID, identité unique du travail
RENDER_HEADER = struct.Struct(">II")
MESSAGES = {
    1: "Le traitement PDF a échoué ; aucun résultat n'est validé.",
    2: "Le PDF est refusé : format, structure ou substitution non pris en charge.",
    3: "Le budget mémoire du traitement PDF est dépassé.",
    4: "La réponse IPC dépasse le budget autorisé.",
    5: "La limite mémoire Windows n'a pas pu être établie ; traitement refusé.",
    6: "Les PDF chiffrés sont refusés.",
    7: "Les formulaires, signatures, annotations et liens sont refusés.",
    8: "La substitution raster multi-images ou réutilisée est refusée.",
    9: "L'espace couleur, le profil ou la transformation d'image est refusé.",
    10: "Le remplacement ne tient pas dans la zone ; agrandir la sélection ou raccourcir le texte.",
    11: "La zone est invalide ou interagit avec un autre contenu ; corriger la sélection.",
    12: "Le PDF ou le rendu dépasse les limites de ressources autorisées.",
    13: "L'export a échoué : vérifier le chemin, l'autorisation de remplacement et les droits d'écriture. Aucune destination partielle n'est validée.",
    14: "Un découpage graphique peut masquer du texte : remplacement refusé, aucun aperçu n'est validé.",
}


class WorkerError(ValueError):
    """Diagnostic parent stable, sans exception ni contenu transmis par l'enfant."""


class UncertainExportError(WorkerError):
    def __init__(self):
        super().__init__("L'état de l'export est incertain : la copie peut déjà avoir été finalisée. "
                         "Contrôlez la destination avant de recommencer ; aucun succès n'est annoncé.")


def _send(sender, status, revision, request_id, payload, limit):
    if HEADER.size + len(payload) > limit:
        status, payload = 4, b""
    try:
        sender.send_bytes(HEADER.pack(status, revision, os.getpid(), request_id) + payload)
    except (OSError, EOFError, MemoryError):
        pass


def _read(receiver, replies, limit):
    try:
        replies.put((True, receiver.recv_bytes(maxlength=limit)))
    except Exception:
        replies.put((False, b""))


def _expire(process, expired):
    expired.set()
    try:
        if process.is_alive():
            process.terminate()
    except (ValueError, OSError):
        pass


def _execute(operation, source, options):
    # Import exclusivement enfant, après établissement du budget natif.
    from substidude.pdf_engine import _open_supported_structure, _open_mupdf, render_page
    from substidude.pipeline import WARNINGS, transform

    if operation == "cleanup":
        from substidude.export import cleanup_abandoned
        return json.dumps({"removed": cleanup_abandoned()}).encode("ascii")
    if operation == "export":
        from substidude.export import write_export
        write_export(source, options["source_path"], options["path"], overwrite=options["overwrite"])
        return b"exported"

    if operation == "open":
        # open_pdf effectue sa lecture bornée, avant parsing ; ne pas relire un
        # chemin susceptible d'avoir changé entre inspection et copie mémoire.
        from substidude.pdf_engine import MAX_FILE_BYTES, _check_file_size
        with open(options["path"], "rb") as stream:
            _check_file_size(stream.seek(0, 2))
            stream.seek(0)
            source = stream.read(MAX_FILE_BYTES)
        with _open_supported_structure(source), _open_mupdf(source):
            return source
    if operation in {"transform", "generate"}:
        zones = [Substitution(**value) for value in options["substitutions"]]
        result = transform(source, zones)
        if operation == "generate":
            from substidude.pdf_engine import classify_zone
            metadata = json.dumps({"modes": [classify_zone(source, z.page, z.rectangle) for z in zones],
                                   "warnings": WARNINGS}).encode("utf-8")
            return struct.pack(">I", len(metadata)) + metadata + result
        return result
    with _open_supported_structure(source), _open_mupdf(source) as document:
        if operation == "inspect":
            return json.dumps({"pages": [{"mediabox": tuple(page.mediabox), "cropbox": tuple(page.cropbox),
                                          "rotation": page.rotation} for page in document],
                               "warnings": WARNINGS}, ensure_ascii=True).encode("ascii")
        page = options["page"]
        if type(page) is not int or not 0 <= page < document.page_count:
            raise SessionError("Page invalide.")
        pixmap = render_page(document[page], options["scale"])
        return RENDER_HEADER.pack(pixmap.width, pixmap.height) + pixmap.samples


def _child(sender, operation, source, encoded_options, revision, request_id, memory_limit, response_limit):
    try:
        from substidude.windows_memory import WindowsMemoryBudget
        try:
            budget = WindowsMemoryBudget(memory_limit)
            budget.__enter__()
        except Exception:
            _send(sender, 5, revision, request_id, b"", response_limit)
            return
        try:
            from substidude.pdf_engine import PDFError
            from substidude.export import ExportError
            try:
                result = _execute(operation, source, json.loads(encoded_options))
                _send(sender, 0, revision, request_id, result, response_limit)
            except PDFError as error:
                # Ne transmet que des codes prédéfinis, jamais str(error).
                message = str(error)
                status = 2
                for words, code in ((('découpage', "boîte d'un Form"), 14),
                                    (('chiffrés',), 6), (('signatures', 'annotations', 'liens'), 7),
                                    (('Plusieurs images', 'réutilisée'), 8),
                                    (('couleur', 'profil', "transformation de cette image"), 9),
                                    (('tient pas',), 10),
                                    (('zone', 'caractère traverse', 'groupe de texte'), 11),
                                    (('limite', '10 Mo', '49 pages', 'mégapixels'), 12)):
                    if any(word in message for word in words):
                        status = code
                        break
                _send(sender, status, revision, request_id, b"", response_limit)
            except SessionError:
                _send(sender, 11, revision, request_id, b"", response_limit)
            except ExportError:
                _send(sender, 13, revision, request_id, b"", response_limit)
        finally:
            budget.__exit__(None, None, None)
    except MemoryError:
        _send(sender, 3, revision, request_id, b"", response_limit)
    except Exception:
        _send(sender, 1, revision, request_id, b"", response_limit)
    finally:
        sender.close()


class PDFJob:
    """Transport issu du banc 11F : spawn, délai global, pipe borné sans pickle de réponse."""

    def __init__(self, *, memory_limit=MAX_PDF_PROCESS_BYTES, duration=MAX_JOB_SECONDS,
                 response_limit=MAX_IPC_BYTES):
        if (type(memory_limit) is not int or not 0 < memory_limit <= MAX_PDF_PROCESS_BYTES
                or type(response_limit) is not int or not HEADER.size <= response_limit <= MAX_IPC_BYTES
                or type(duration) not in (int, float) or not isfinite(duration) or not 0 < duration <= MAX_JOB_SECONDS):
            raise WorkerError("Budget de traitement invalide.")
        self.memory_limit, self.duration, self.response_limit = memory_limit, duration, response_limit
        self.context = multiprocessing.get_context("spawn")
        self.process = self.receiver = self.reader = self.replies = None
        self.started = self.timer = self.expired = self.request_id = self.revision = None
        self.operation = None

    @property
    def done(self):
        return self.process is not None and (self.expired.is_set()
            or (not self.replies.empty() and not self.process.is_alive()))

    def start(self, operation, source=b"", *, substitutions=(), page=0, scale=1, path=None, revision=0,
              source_path=None, overwrite=False):
        if self.process is not None:
            raise WorkerError("Un travail PDF est déjà actif ou non collecté.")
        if (operation not in {"open", "inspect", "render", "transform", "generate", "export", "cleanup"} or type(source) is not bytes
                or type(revision) is not int or not 0 <= revision < 2**63
                or (operation not in {"open", "cleanup"} and not 0 < len(source) < 10_000_000)
                or (operation == "open" and (not isinstance(path, str) or not path or source))):
            raise WorkerError("Commande de traitement invalide.")
        options = {}
        if operation == "open":
            options["path"] = path
        elif operation == "export":
            if (not isinstance(path, str) or not path or not isinstance(source_path, str)
                    or not source_path or type(overwrite) is not bool):
                raise WorkerError("Paramètres d'export invalides.")
            if self.response_limit < HEADER.size + len(b"exported"):
                raise WorkerError("Le budget IPC ne permet pas l'accusé d'export ; aucune écriture lancée.")
            options.update(path=path, source_path=source_path, overwrite=overwrite)
        elif operation == "render":
            if (type(page) is not int or page < 0 or type(scale) not in (int, float)
                    or not isfinite(scale) or scale <= 0):
                raise WorkerError("Paramètres de rendu invalides.")
            options.update(page=page, scale=scale)
        elif operation in {"transform", "generate"}:
            try:
                options["substitutions"] = [vars(zone) for zone in validate_substitutions(substitutions)]
            except SessionError:
                raise WorkerError("Substitutions invalides.") from None
        try:
            encoded = json.dumps(options, ensure_ascii=True, allow_nan=False).encode("ascii")
        except (ValueError, TypeError, OverflowError):
            raise WorkerError("Commande de traitement invalide.") from None
        if len(encoded) + len(source) + HEADER.size > MAX_IPC_BYTES:
            raise WorkerError("La demande IPC dépasse le budget autorisé.")
        self.receiver, sender = self.context.Pipe(duplex=False)
        self.request_id, self.revision = uuid4().bytes, revision
        self.operation = operation
        self.process = self.context.Process(target=_child, args=(
            sender, operation, source, encoded, revision, self.request_id, self.memory_limit, self.response_limit))
        try:
            self.started = monotonic()
            self.process.start()
            self.expired = Event()
            self.timer = Timer(max(0, self.duration - (monotonic() - self.started)),
                               _expire, args=(self.process, self.expired))
            self.timer.daemon = True
            self.timer.start()
            self.replies = Queue(maxsize=1)
            self.reader = Thread(target=_read, args=(self.receiver, self.replies, self.response_limit),
                                 name="SubstiDudePDFIPC", daemon=True)
            self.reader.start()
        except Exception:
            self.cancel()
            raise WorkerError("Le processus PDF n'a pas pu démarrer.") from None
        finally:
            sender.close()

    def cancel(self):
        if self.process is None:
            return
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
        self.process = self.receiver = self.reader = self.replies = None
        self.timer = self.expired = self.started = self.request_id = self.revision = None
        self.operation = None

    def receive(self):
        if self.process is None:
            raise WorkerError("Aucun travail PDF actif.")
        exporting, definite_failure = self.operation == "export", False
        try:
            remaining = self.duration - (monotonic() - self.started)
            if remaining <= 0 or self.expired.is_set():
                raise WorkerError("Le délai du traitement PDF est dépassé.")
            valid, packet = self.replies.get(timeout=remaining)
            if not valid or len(packet) < HEADER.size:
                raise WorkerError("La réponse IPC est invalide, trop grande ou absente.")
            status, revision, pid, request_id = HEADER.unpack_from(packet)
            remaining = self.duration - (monotonic() - self.started)
            if remaining <= 0 or self.expired.is_set():
                raise WorkerError("Le délai du traitement PDF est dépassé.")
            self.process.join(timeout=remaining)
            if self.process.is_alive() or self.expired.is_set() or monotonic() - self.started >= self.duration:
                raise WorkerError("Le délai du traitement PDF est dépassé.")
            if (self.process.exitcode != 0 or pid != self.process.pid or pid == os.getpid()
                    or request_id != self.request_id or revision != self.revision):
                raise WorkerError("Le résultat PDF est invalide ou périmé.")
            if status != 0:
                definite_failure = status in {5, 13}
                raise WorkerError(MESSAGES.get(status, MESSAGES[1]))
            if exporting and packet[HEADER.size:] != b"exported":
                raise WorkerError("L'accusé d'export est invalide.")
            return packet[HEADER.size:]
        except Empty:
            if exporting:
                raise UncertainExportError() from None
            raise WorkerError("Le délai du traitement PDF est dépassé.") from None
        except (OSError, EOFError):
            if exporting:
                raise UncertainExportError() from None
            raise WorkerError("Le processus PDF s'est arrêté sans résultat.") from None
        except WorkerError:
            if exporting and not definite_failure:
                raise UncertainExportError() from None
            raise
        finally:
            self.cancel()

    def __enter__(self):
        return self

    def __exit__(self, *ignored):
        self.cancel()


class SessionController:
    """Lie un travail contrôlé à une session/révision ; jamais de confirmation implicite."""

    def __init__(self, session):
        self.session, self.job, self.generation = session, PDFJob(), None

    def generate(self):
        if self.job.process is not None:
            raise WorkerError("Un travail PDF est déjà actif ou non collecté.")
        generation = self.session.begin_generation()
        try:
            self.job.start("transform", self.session.source, substitutions=self.session.substitutions,
                           revision=generation.revision)
            self.generation = generation
        except Exception:
            self.session.fail_generation(generation)
            raise

    def collect(self):
        generation = self.generation
        try:
            result = self.job.receive()
            return self.session.accept_result(generation, result)
        except Exception:
            self.session.fail_generation(generation)
            raise
        finally:
            self.generation = None

    def cancel(self):
        self.job.cancel()
        self.session.fail_generation(self.generation)
        self.generation = None

    def close(self):
        self.cancel()

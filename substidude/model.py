# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""État de session indépendant de Qt et des bibliothèques PDF."""

from dataclasses import dataclass
from math import isfinite
from uuid import uuid4

WARNINGS = (
    "Des copies cachées peuvent subsister dans les représentations différées ; aucune anonymisation exhaustive n'est garantie.",
    "Les remplacements raster sont intégrés aux pixels, sans nouvelle couche OCR.",
)


class SessionError(ValueError):
    """Erreur neutre de validation ou de cycle de vie."""


@dataclass(frozen=True)
class Substitution:
    page: int
    rectangle: tuple
    text: str = ""

    def __post_init__(self):
        try:
            rect = tuple(self.rectangle)
            valid = (type(self.page) is int and self.page >= 0 and len(rect) == 4
                     and all(type(v) in (int, float) and isfinite(v) for v in rect)
                     and 0 <= rect[0] < rect[2] and 0 <= rect[1] < rect[3]
                     and isinstance(self.text, str))
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            raise SessionError("Les paramètres de substitution sont invalides.")
        object.__setattr__(self, "rectangle", rect)


def validate_substitutions(values):
    if not isinstance(values, (list, tuple)) or not values or any(type(v) is not Substitution for v in values):
        raise SessionError("Au moins une substitution valide est nécessaire.")
    for index, zone in enumerate(values):
        x0, y0, x1, y1 = zone.rectangle
        for other in values[:index]:
            a, b, c, d = other.rectangle
            if zone.page == other.page and max(x0, a) < min(x1, c) and max(y0, b) < min(y1, d):
                raise SessionError("Les zones se chevauchent ; corriger les sélections.")
    return tuple(values)


@dataclass(frozen=True)
class Generation:
    session: str
    revision: int
    request: str


class Session:
    """N'accepte que le résultat du dernier travail de sa révision courante.

    accept_result est réservé au contrôleur après vérification par le worker.
    Ce modèle n'est pas une frontière de sécurité contre du code Python appelant.
    """

    def __init__(self, source):
        if type(source) is not bytes or not source:
            raise SessionError("L'original doit être une copie immuable non vide.")
        self._source = source
        self._identity = uuid4().hex
        self._revision = 0
        self._substitutions = ()
        self._pending = None
        self._result = None
        self._confirmed = None
        self._exported = None

    @property
    def source(self):
        return self._source

    @property
    def revision(self):
        return self._revision

    @property
    def substitutions(self):
        return self._substitutions

    @property
    def result(self):
        return self._result

    @property
    def state(self):
        if self._exported is not None and self._exported == (self.revision, self._result):
            return "Exporté"
        return "Vérifié par l'utilisateur" if self._confirmed is not None else "À vérifier"

    @property
    def warnings(self):
        return WARNINGS

    def set_substitutions(self, values):
        # Une liste vide permet la suppression de la dernière zone.
        zones = () if isinstance(values, (list, tuple)) and not values else validate_substitutions(values)
        self._substitutions = zones
        self._revision += 1
        self._pending = self._result = self._confirmed = self._exported = None

    def begin_generation(self):
        validate_substitutions(self.substitutions)
        self._pending = Generation(self._identity, self.revision, uuid4().hex)
        self._result = self._confirmed = self._exported = None
        return self._pending

    def accept_result(self, generation, data):
        if generation != self._pending or generation is None:
            return False
        if type(data) is not bytes or not data:
            self.fail_generation(generation)
            raise SessionError("Le résultat vérifié est absent.")
        self._result = data
        self._pending = self._confirmed = None
        return True

    def fail_generation(self, generation):
        if generation is not None and generation == self._pending:
            self._pending = self._result = self._confirmed = None

    def confirm(self):
        if self._result is None or self._pending is not None:
            raise SessionError("Régénérer et vérifier le résultat avant confirmation.")
        self._confirmed = (self.revision, self._result)

    def unconfirm(self):
        self._confirmed = None
        self._exported = None

    def mark_exported(self, data):
        if data is not self.confirmed_bytes():
            raise SessionError("L'export ne correspond pas aux octets confirmés.")
        self._exported = (self.revision, self._result)

    def begin_export(self):
        data = self.confirmed_bytes()
        self._exported = None
        return data

    def confirmed_bytes(self):
        if self._confirmed != (self.revision, self._result) or self._result is None:
            raise SessionError("La version courante du résultat n'est pas confirmée.")
        return self._result

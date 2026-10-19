# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

import unittest

from substidude.model import Session, SessionError, Substitution


class ModelTests(unittest.TestCase):
    def test_substitutions_are_immutable_and_validate_values(self):
        zone = Substitution(0, [1, 2, 80, 60], "Société Élodie\nToto")
        self.assertEqual((1, 2, 80, 60), zone.rectangle)
        for values in ((True, (1, 2, 3, 4), "Toto"),
                       (0, (1, 2, 1, 4), "Toto"), (0, (0, 0, float("inf"), 4), "Toto"),
                       (0, (1, 2, 3, 4), None)):
            with self.subTest(values=values), self.assertRaises(SessionError):
                Substitution(*values)
        for options in ({"font_size": 12}, {"background": (1, 1, 1)}):
            with self.subTest(options=options), self.assertRaises(TypeError):
                Substitution(0, (1, 2, 3, 4), "Toto", **options)

    def test_confirmation_is_bound_to_exact_result_and_revision(self):
        session = Session(b"synthetic-source")
        session.set_substitutions([Substitution(0, (1, 2, 80, 60), "Toto")])
        ticket = session.begin_generation()
        with self.assertRaises(SessionError):
            session.confirm()
        self.assertTrue(session.accept_result(ticket, b"verified-result"))
        self.assertEqual("À vérifier", session.state)
        session.confirm()
        self.assertEqual(b"verified-result", session.confirmed_bytes())
        self.assertEqual("Vérifié par l'utilisateur", session.state)
        session.set_substitutions([Substitution(0, (1, 2, 80, 60), "John Doe")])
        self.assertIsNone(session.result)
        with self.assertRaises(SessionError):
            session.confirmed_bytes()
        self.assertFalse(session.accept_result(ticket, b"old-result"))

    def test_stale_sessions_retries_and_failure_cannot_restore_confirmation(self):
        session = Session(b"source")
        session.set_substitutions([Substitution(0, (1, 2, 80, 60), "")])
        first = session.begin_generation()
        second = session.begin_generation()
        self.assertFalse(session.accept_result(first, b"old"))
        session.fail_generation(second)
        self.assertFalse(session.accept_result(second, b"late"))
        other = Session(b"other")
        self.assertFalse(other.accept_result(first, b"wrong-session"))
        third = session.begin_generation()
        self.assertTrue(session.accept_result(third, b"new"))
        session.confirm()
        session.begin_generation()
        with self.assertRaises(SessionError):
            session.confirmed_bytes()

    def test_invalid_updates_do_not_mutate_session(self):
        session = Session(b"source")
        zone = Substitution(0, (1, 2, 80, 60), "Toto")
        session.set_substitutions([zone])
        revision = session.revision
        with self.assertRaises(SessionError):
            session.set_substitutions([zone, zone])
        self.assertEqual(revision, session.revision)
        self.assertEqual((zone,), session.substitutions)

    def test_empty_edit_invalidation_and_source_is_read_only(self):
        session = Session(b"source")
        with self.assertRaises(AttributeError):
            session.source = b"other"
        self.assertTrue(session.warnings)
        session.set_substitutions([Substitution(0, (1, 2, 80, 60), "Toto")])
        ticket = session.begin_generation()
        session.accept_result(ticket, b"verified")
        session.confirm()
        session.fail_generation(None)
        self.assertEqual(b"verified", session.confirmed_bytes())
        session.set_substitutions([])
        self.assertIsNone(session.result)
        with self.assertRaises(SessionError):
            session.begin_generation()


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch, MagicMock
from contextlib import redirect_stdout, redirect_stderr
import io
import imaplib
from scripts.contact_retention_audit import main, AuditError
from datetime import datetime, timezone
from scripts.contact_retention_audit import anniversary, parse_message, review, scan, folders_from_list, OWN

NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)
OLD = datetime(2025, 1, 1, tzinfo=timezone.utc)
def msg(folder='SansSuite', date=OLD, keys=None, uid='1'):
    return dict(folder=folder, date=date, keys=keys or {'address:client@example.org'}, external=True, uid=uid, uidvalidity='42')

class RetentionTests(unittest.TestCase):
    def evaluate(self, messages):
        return review(messages, 'SansSuite', {'Sent'}, NOW)[0]
    def test_old_needs_manual_review(self):
        self.assertEqual(self.evaluate([msg()])['status'], 'a_verifier_manuellement')
    def test_recent_sent_reply_blocks(self):
        result = self.evaluate([msg(), msg('Sent', NOW)])
        self.assertIn('moins_de_12_mois_ou_date_future', result['reasons'])
    def test_any_other_folder_protects(self):
        for folder in ('Clients', 'Devis', 'INBOX', 'Trash', 'Archives'):
            self.assertIn('echange_dans_un_autre_dossier', self.evaluate([msg(), msg(folder)])['reasons'])
    def test_transitive_reference_links(self):
        a = msg(keys={'id:a'})
        b = msg('Sent', keys={'id:a', 'id:b'})
        c = msg('Clients', keys={'id:b'})
        self.assertEqual(self.evaluate([a, b, c])['status'], 'bloque')
    def test_unrelated_client_not_linked(self):
        self.assertEqual(self.evaluate([msg(), msg('Clients', keys={'address:other@example.org'})])['status'], 'a_verifier_manuellement')
    def test_leap_anniversary(self):
        self.assertEqual(anniversary(datetime(2024, 2, 29, tzinfo=timezone.utc)), datetime(2025, 2, 28, tzinfo=timezone.utc))
    def test_exact_anniversary(self):
        self.assertEqual(self.evaluate([msg(date=NOW.replace(year=2025))])['status'], 'a_verifier_manuellement')
    def test_reply_to_and_latest_date(self):
        raw = b'Date: Wed, 1 Jan 2025 00:00:00 +0000\r\nMessage-ID: <a@example.org>\r\nFrom: contact@jalauris.fr\r\nTo: solution@jalauris.fr\r\nReply-To: client@example.org\r\n\r\n'
        parsed = parse_message('SansSuite', '42', '1', b'1 (UID 1 INTERNALDATE "19-Nov-2026 00:00:00 +0000")', raw, OWN)
        self.assertIn('address:client@example.org', parsed['keys'])
        self.assertNotIn('address:contact@jalauris.fr', parsed['keys'])
        self.assertEqual(parsed['date'], NOW)
    def test_missing_date_aborts(self):
        with self.assertRaises((ValueError, TypeError)):
            parse_message('SansSuite', '42', '1', b'INTERNALDATE "01-Jan-2025 00:00:00 +0000"', b'Message-ID: <a@b>\r\n', OWN)
    def test_negative_zero_zone_is_utc(self):
        raw = b'Date: Thu, 19 Nov 2026 15:00:00 -0000\r\nMessage-ID: <a@b>\r\nFrom: client@example.org\r\n\r\n'
        m = parse_message('SansSuite', '42', '1', b'INTERNALDATE "19-Nov-2026 15:00:00 +0100"', raw, OWN)
        self.assertEqual(m['date'], datetime(2026, 11, 19, 15, tzinfo=timezone.utc))
        self.assertEqual(self.evaluate([m])['status'], 'bloque')

    def test_missing_or_unknown_zone_not_inferred(self):
        for zone in ('', 'UNKNOWN'):
            raw = ('Date: Thu, 19 Nov 2026 15:00:00 ' + zone + '\r\nMessage-ID: <a@b>\r\n\r\n').encode()
            with self.assertRaisesRegex(AuditError, 'Fuseau horaire du message'):
                parse_message('SansSuite', '42', '1', b'INTERNALDATE "19-Nov-2026 15:00:00 +0000"', raw, OWN)

    def test_multiple_dates_rejected(self):
        raw = b'Date: Thu, 19 Nov 2026 15:00:00 +0000\r\nDate: Wed, 1 Jan 2025 00:00:00 +0000\r\nMessage-ID: <a@b>\r\n'
        with self.assertRaisesRegex(AuditError, 'multiple'):
            parse_message('SansSuite', '42', '1', b'INTERNALDATE "19-Nov-2026 15:00:00 +0000"', raw, OWN)

    def test_missing_id_reported_without_omitting_message(self):
        raw = b'Date: Wed, 1 Jan 2025 00:00:00 +0000\r\nFrom: other@example.org\r\n\r\n'
        m = parse_message('INBOX', '42', '9', b'INTERNALDATE "01-Jan-2025 00:00:00 +0000"', raw, OWN)
        self.assertEqual(m['issues'], ['message_id_absent_ou_ambigu'])
        result = self.evaluate([msg(), m])
        self.assertEqual(result['status'], 'bloque')
        self.assertIn('identifiants_incomplets_dans_la_boite_verification_manuelle_requise', result['reasons'])

    def test_multiple_or_malformed_ids_block_all_candidates(self):
        for header in (b'Message-ID: malformed\r\n', b'Message-ID: <a@b>\r\nMessage-ID: <c@d>\r\n'):
            raw = b'Date: Wed, 1 Jan 2025 00:00:00 +0000\r\n' + header + b'From: other@example.org\r\n\r\n'
            m = parse_message('Sent', '42', '9', b'INTERNALDATE "01-Jan-2025 00:00:00 +0000"', raw, OWN)
            self.assertTrue(m['issues'])
            self.assertEqual(self.evaluate([msg(), m])['status'], 'bloque')

    def test_list_parsing_and_abort(self):
        self.assertEqual(folders_from_list([b'(\\Noselect) "/" "Parent"', b'(\\Sent) "/" "Sent"']), ['Sent'])
        with self.assertRaises(ValueError):
            folders_from_list([(b'() "/" {4}', b'Sent')])
    def test_scan_only_uses_read_commands(self):
        class Fake:
            def list(self, *args): return 'OK', [b'() "/" "SansSuite"', b'(\\Sent) "/" "Sent"']
            def select(self, folder, readonly):
                assert readonly is True
                return 'OK', [b'0']
            def response(self, key): return key, [b'42']
            def uid(self, command, *args):
                assert command == 'SEARCH'
                return 'OK', [b'']
        self.assertEqual(scan(Fake(), 'SansSuite', {'Sent'}, OWN, 10), [])
    def test_missing_sent_folder_aborts(self):
        class Fake:
            def list(self, *args): return 'OK', [b'() "/" "SansSuite"']
        with self.assertRaises(ValueError):
            scan(Fake(), 'SansSuite', {'Sent'}, OWN, 10)

class DiagnosticTests(unittest.TestCase):
    def test_list_only_never_selects_or_fetches(self):
        client = MagicMock()
        client.login.return_value = ('OK', [b'ok'])
        client.list.return_value = ('OK', [b'() "/" "Sent"'])
        client.__enter__.return_value = client
        output = io.StringIO()
        with patch('sys.argv', ['audit', '--list-folders']), patch.dict('os.environ', {'JALAURIS_IMAP_PASSWORD': 'private-secret'}), patch('imaplib.IMAP4_SSL', return_value=client), redirect_stdout(output), redirect_stderr(io.StringIO()):
            main()
        self.assertIn('Sent', output.getvalue())
        self.assertNotIn('private-secret', output.getvalue())
        client.select.assert_not_called()
        client.uid.assert_not_called()

    def test_login_failure_hides_server_text(self):
        client = MagicMock()
        client.__enter__.return_value = client
        client.login.side_effect = imaplib.IMAP4.error('sensitive server response')
        with patch('sys.argv', ['audit', '--list-folders']), patch.dict('os.environ', {'JALAURIS_IMAP_PASSWORD': 'private-secret'}), patch('imaplib.IMAP4_SSL', return_value=client):
            with self.assertRaises(AuditError) as error:
                main()
        self.assertIn('authentification', str(error.exception))
        self.assertNotIn('sensitive', str(error.exception))
        self.assertNotIn('private-secret', str(error.exception))

if __name__ == '__main__': unittest.main()

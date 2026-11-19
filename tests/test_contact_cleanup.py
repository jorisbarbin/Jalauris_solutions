import copy
from datetime import datetime, timezone
import imaplib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from scripts import contact_retention_cleanup as cleanup
from scripts import contact_retention_audit as audit

NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)


def mail(uid, address='client@example.org', date='Wed, 1 Jan 2025 00:00:00 +0000', flags=(), internal='01-Jan-2025 00:00:00 +0000'):
    return {'uid': str(uid), 'raw': ('Date: '+date+'\r\nMessage-ID: <m'+str(uid)+'@example.org>\r\nFrom: '+address+'\r\nTo: solution@jalauris.fr\r\n\r\n').encode(), 'flags': list(flags), 'modseq': 1, 'internal': internal}


class FakeIMAP:
    def __init__(self):
        self.boxes = {cleanup.CANDIDATE: [mail(1)], 'Sent': [], 'INBOX': []}
        self.revisions = {k: 10 for k in self.boxes}
        self.validities = {k: 123 for k in self.boxes}
        self.nexts = {k: 100 for k in self.boxes}
        self.selected = None
        self.calls = []
        self.modified = [None]
        self.on_mark = None
        self.fail_expunge = False
        self.concurrent_store = False
    def list(self, *args):
        return 'OK', [('() "/" "'+k+'"').encode() for k in self.boxes]
    def select(self, folder, readonly=True):
        self.selected = folder.strip('"')
        return 'OK', [str(len(self.boxes[self.selected])).encode()]
    def response(self, key):
        if key == 'UIDVALIDITY': return key, [str(self.validities[self.selected]).encode()]
        value, self.modified = self.modified, [None]
        return key, value
    def status(self, folder, items):
        f = folder.strip('"')
        return 'OK', [('"'+f+'" (MESSAGES '+str(len(self.boxes[f]))+' UIDNEXT '+str(self.nexts[f])+' UIDVALIDITY '+str(self.validities[f])+' HIGHESTMODSEQ '+str(self.revisions[f])+')').encode()]
    def create(self, folder):
        name = folder.strip('"')
        assert name not in self.boxes
        self.boxes[name] = []
        self.validities[name] = 987
        self.revisions[name] = 10
        self.nexts[name] = 1
        return 'OK', []
    def append(self, folder, flags, date, body):
        name = folder.strip('"')
        uid = self.nexts[name]
        self.nexts[name] += 1
        self.revisions[name] += 1
        self.boxes[name].append({'uid': str(uid), 'raw': body, 'flags': ['\\Deleted'] if flags else [], 'modseq': self.revisions[name], 'internal': date.strip('"')})
        return 'OK', []
    def delete(self, folder):
        name = folder.strip('"')
        assert name.startswith('JALAURIS-retention-test-') and not self.boxes[name]
        del self.boxes[name]
        return 'OK', []
    def uid(self, command, *args):
        self.calls.append((command, args))
        box = self.boxes[self.selected]
        if command == 'SEARCH': return 'OK', [' '.join(m['uid'] for m in box).encode()]
        if command == 'FETCH':
            uid = args[0].decode() if isinstance(args[0], bytes) else args[0]
            matches = [m for m in box if m['uid'] == uid]
            if not matches: return 'OK', [None]
            m = matches[0]
            metadata = ('1 (UID '+uid+' FLAGS ('+' '.join(m['flags'])+') MODSEQ ('+str(m['modseq'])+') INTERNALDATE "'+m['internal']+'" BODY[HEADER.FIELDS] {'+str(len(m['raw']))+'}').encode()
            return 'OK', [(metadata, m['raw']), b')']
        if command == 'STORE':
            targets = set(args[0].split(','))
            if any('+FLAGS.SILENT' in arg for arg in args):
                if self.concurrent_store:
                    self.modified = [args[0].encode()]
                    return 'OK', [b'changed']
                for m in box:
                    if m['uid'] in targets:
                        self.revisions[self.selected] += 1
                        m['modseq'] = self.revisions[self.selected]
                        m['flags'].append('\\Deleted')
                if self.on_mark:
                    self.on_mark(self)
            elif '-FLAGS.SILENT' in args:
                for m in box:
                    if m['uid'] in targets:
                        self.revisions[self.selected] += 1
                        m['modseq'] = self.revisions[self.selected]
                        m['flags'] = [f for f in m['flags'] if f != '\\Deleted']
            else: raise AssertionError('Unexpected STORE')
            return 'OK', [b'ok']
        if command == 'EXPUNGE':
            targets = set(args[0].split(','))
            if self.fail_expunge:
                # Ambiguous network failure: no automatic retry is permissible.
                raise imaplib.IMAP4.abort('sensitive server content')
            self.boxes[self.selected] = [m for m in box if not (m['uid'] in targets and '\\Deleted' in m['flags'])]
            self.revisions[self.selected] += 1
            return 'OK', [b'ok']
        raise AssertionError('Unexpected command '+command)


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.client = FakeIMAP()
        self.config = {'candidate_uidvalidity': 123}
        self.clock = patch.object(cleanup, 'utcnow', return_value=NOW)
        self.clock.start()
    def tearDown(self):
        self.clock.stop()
        self.tmp.cleanup()
    def run_cleanup(self, apply=True):
        return cleanup.execute(self.client, self.config, self.root, apply=apply)
    def assert_no_writes(self):
        self.assertFalse(any(c[0] in ('STORE', 'EXPUNGE') for c in self.client.calls))
    def test_old_classified_message_deleted_and_sentinel_preserved(self):
        self.client.boxes[cleanup.CANDIDATE].append(mail(2, address='other@example.org', flags=['\\Deleted']))
        result = self.run_cleanup()
        self.assertEqual(result['deleted_messages'], 1)
        self.assertEqual([m['uid'] for m in self.client.boxes[cleanup.CANDIDATE]], ['2'])
        self.assertEqual([c for c in self.client.calls if c[0] == 'EXPUNGE'], [('EXPUNGE', ('1',))])
        self.assertFalse((self.root/'pending.json').exists())
    def test_simulation_never_writes(self):
        self.assertEqual(self.run_cleanup(False)['eligible_messages'], 1)
        self.assert_no_writes()
        self.assertFalse((self.root/'pending.json').exists())
    def test_recent_sent_reply_blocks(self):
        self.client.boxes['Sent'] = [mail(3, date='Thu, 19 Nov 2026 12:00:00 +0000')]
        self.assertEqual(self.run_cleanup()['deleted_messages'], 0)
        self.assert_no_writes()
    def test_old_sent_copy_still_needs_classification(self):
        self.client.boxes['Sent'] = [mail(3)]
        self.assertEqual(self.run_cleanup()['deleted_messages'], 0)
        self.assert_no_writes()
    def test_client_folder_blocks(self):
        self.client.boxes['INBOX'] = [mail(3)]
        self.assertEqual(self.run_cleanup()['deleted_messages'], 0)
        self.assert_no_writes()
    def test_flagged_or_draft_never_deleted(self):
        for flag in ('\\Flagged', '\\Draft'):
            self.client.boxes[cleanup.CANDIDATE][0]['flags'] = [flag]
            self.assertEqual(self.run_cleanup()['deleted_messages'], 0)
        self.assert_no_writes()
    def test_missing_message_id_blocks_all(self):
        m = mail(3, address='other@example.org')
        m['raw'] = m['raw'].replace(b'Message-ID: <m3@example.org>\r\n', b'')
        self.client.boxes['INBOX'] = [m]
        self.assertEqual(self.run_cleanup()['deleted_messages'], 0)
        self.assert_no_writes()
    def test_uidvalidity_change_blocks(self):
        self.client.validities[cleanup.CANDIDATE] = 456
        with self.assertRaisesRegex(audit.AuditError, 'recréé'):
            self.run_cleanup()
        self.assert_no_writes()
    def test_volume_cap_refuses_entire_batch(self):
        self.client.boxes[cleanup.CANDIDATE] = [mail(i) for i in range(1, 22)]
        with self.assertRaisesRegex(audit.AuditError, 'Plafond'):
            self.run_cleanup()
        self.assert_no_writes()
    def test_pending_operation_blocks_retry(self):
        (self.root/'pending.json').write_text('{}')
        with self.assertRaisesRegex(audit.AuditError, 'précédente'):
            self.run_cleanup()
        self.assertEqual(self.client.calls, [])
    def test_concurrent_new_reply_after_mark_undoes_flags_and_stops(self):
        def reply(client):
            client.boxes['Sent'].append(mail(3, date='Thu, 19 Nov 2026 12:00:00 +0000'))
            client.revisions['Sent'] += 1
        self.client.on_mark = reply
        with self.assertRaises(audit.AuditError):
            self.run_cleanup()
        self.assertEqual(self.client.boxes[cleanup.CANDIDATE][0]['flags'], [])
        self.assertFalse(any(c[0] == 'EXPUNGE' for c in self.client.calls))
        self.assertTrue((self.root/'pending.json').exists())
    def test_conditional_store_conflict_never_expunges(self):
        self.client.concurrent_store = True
        with self.assertRaisesRegex(audit.AuditError, 'modifiés'):
            self.run_cleanup()
        self.assertFalse(any(c[0] == 'EXPUNGE' for c in self.client.calls))
    def test_network_failure_keeps_journal_and_blocks_retry(self):
        self.client.fail_expunge = True
        with self.assertRaises(imaplib.IMAP4.abort):
            self.run_cleanup()
        self.assertTrue((self.root/'pending.json').exists())
        before = len(self.client.calls)
        with self.assertRaisesRegex(audit.AuditError, 'précédente'):
            self.run_cleanup()
        self.assertEqual(len(self.client.calls), before)
    def test_changed_snapshot_never_marks(self):
        original = cleanup.snapshot
        count = 0
        def modified(client):
            nonlocal count
            count += 1
            if count == 2:
                client.boxes['INBOX'].append(mail(3))
            return original(client)
        with patch.object(cleanup, 'snapshot', side_effect=modified), self.assertRaisesRegex(audit.AuditError, 'Inventaire'):
            self.run_cleanup()
        self.assert_no_writes()
    def test_live_selftest_uses_only_temporary_messages(self):
        before = copy.deepcopy(self.client.boxes)
        cleanup.live_self_test(self.client)
        self.assertEqual(self.client.boxes, before)
        self.assertEqual(len([c for c in self.client.calls if c[0] == 'EXPUNGE']), 2)

    def test_live_selftest_detects_wrong_server_expunge_behavior(self):
        original = self.client.uid
        def faulty(command, *args):
            if command == 'EXPUNGE':
                self.client.boxes[self.client.selected] = []
                return 'OK', []
            return original(command, *args)
        before = copy.deepcopy(self.client.boxes[cleanup.CANDIDATE])
        self.client.uid = faulty
        with self.assertRaisesRegex(audit.AuditError, 'Test UID EXPUNGE'):
            cleanup.live_self_test(self.client)
        self.assertEqual(self.client.boxes[cleanup.CANDIDATE], before)

    def test_uidset_rejects_wildcard_ranges_and_empty(self):
        for uids in ([], ['*'], ['1:20'], ['1','1'], ['0'], ['1,2']):
            with self.assertRaises(audit.AuditError): cleanup.uidset(uids)
    def test_missing_condstore_metadata_aborts(self):
        self.client.boxes[cleanup.CANDIDATE][0]['modseq'] = 'missing'
        with self.assertRaisesRegex(audit.AuditError, 'Suivi'):
            self.run_cleanup()
        self.assert_no_writes()
    def test_global_lock_refuses_concurrent_execution(self):
        with cleanup.lock(self.root):
            with self.assertRaisesRegex(audit.AuditError, 'autre exécution'):
                with cleanup.lock(self.root): pass
    def test_unsafe_state_permissions_refused(self):
        self.root.chmod(0o755)
        with self.assertRaisesRegex(audit.AuditError, 'autre utilisateur'):
            cleanup.secure_state(self.root)
    def test_status_files_are_private(self):
        cleanup.write_json(self.root/'test.json', {'ok': True})
        self.assertEqual((self.root/'test.json').stat().st_mode & 0o777, 0o600)


class PrerequisiteTests(unittest.TestCase):
    def test_missing_capabilities_refuses_connection(self):
        client = MagicMock()
        client.login.return_value = ('OK', [])
        client.capability.return_value = ('OK', [b'IMAP4rev1 UIDPLUS'])
        with patch.object(cleanup.imaplib, 'IMAP4_SSL', return_value=client):
            with self.assertRaisesRegex(audit.AuditError, 'CONDSTORE'):
                cleanup.connect('not-a-real-secret')
        client.enable.assert_not_called()
        client.logout.assert_called_once()

    def test_conditional_store_compatible_with_installed_imaplib(self):
        client = object.__new__(imaplib.IMAP4)
        client.state = 'SELECTED'
        client._simple_command = MagicMock(return_value=('OK', [b'ok']))
        client._untagged_response = MagicMock(return_value=('OK', []))
        client.uid('STORE', '1,2', '(UNCHANGEDSINCE 42) +FLAGS.SILENT', '(\\Deleted)')
        client._simple_command.assert_called_once_with('UID', 'STORE', '1,2', '(UNCHANGEDSINCE 42) +FLAGS.SILENT', '(\\Deleted)')

    def test_capabilities_enable_condstore(self):
        client = MagicMock()
        client.login.return_value = ('OK', [])
        client.capability.return_value = ('OK', [b'IMAP4rev1 UIDPLUS ENABLE CONDSTORE'])
        client.enable.return_value = ('OK', [])
        with patch.object(cleanup.imaplib, 'IMAP4_SSL', return_value=client):
            self.assertIs(cleanup.connect('not-a-real-secret'), client)
        client.enable.assert_called_once_with('CONDSTORE')

    def test_unconfigured_run_never_reads_keychain(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cleanup, 'STATE', Path(tmp)), patch('sys.argv', ['cleanup', 'run']), patch.object(cleanup.keychain, 'read') as secret:
            with self.assertRaisesRegex(audit.AuditError, 'Configuration locale'):
                cleanup.main()
            secret.assert_not_called()

    def test_modified_code_requires_revalidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cleanup.write_json(root / 'config.json', {'enabled': True, 'all_exchanges_in_gandi': True, 'self_test_at': NOW.isoformat(), 'code_digest': 'obsolete'})
            with patch.object(cleanup, 'STATE', root), patch('sys.argv', ['cleanup', 'run']), patch.object(cleanup.keychain, 'read') as secret:
                with self.assertRaisesRegex(audit.AuditError, 'Programme modifié'):
                    cleanup.main()
                secret.assert_not_called()

    def test_failed_setup_remains_disabled(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cleanup.getpass, 'getpass', return_value='not-a-real-secret'), patch.object(cleanup, 'connect', side_effect=audit.AuditError('UIDPLUS requis')), patch('sys.stdout', new=io.StringIO()):
            root = Path(tmp)
            cleanup.write_json(root / 'config.json', {'enabled': True})
            with self.assertRaises(audit.AuditError): cleanup.configure(root)
            self.assertFalse(cleanup.json.loads((root / 'config.json').read_text())['enabled'])

if __name__ == '__main__': unittest.main()

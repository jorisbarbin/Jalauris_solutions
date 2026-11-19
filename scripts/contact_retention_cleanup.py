#!/usr/bin/env python3
"""Bounded IMAP cleanup: only the explicitly classified folder, never global EXPUNGE."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import format_datetime
import fcntl
import getpass
import hashlib
import imaplib
import json
import os
from pathlib import Path
import re
import ssl
import sys
import tempfile
import uuid

if __package__:
    from . import contact_retention_audit as audit
    from . import retention_keychain as keychain
else:
    import contact_retention_audit as audit
    import retention_keychain as keychain

STATE = Path(__file__).resolve().parents[2] / '.jalauris-retention'
CANDIDATE = 'Demandes sans suite'
SENT = {'Sent'}
MAX_BATCH = 20
UTC = timezone.utc


def utcnow():
    return datetime.now(UTC)


def quote(folder):
    return '"' + folder.replace('\\', '\\\\').replace('"', '\\"') + '"'


def uidset(uids):
    if not uids or len(set(uids)) != len(uids) or any(not re.fullmatch(r'[1-9][0-9]*', u) for u in uids):
        raise audit.AuditError('Liste UID invalide')
    return ','.join(sorted(uids, key=int))


def secure_state(root):
    if root.is_symlink():
        raise audit.AuditError('Dossier de configuration non sûr')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise audit.AuditError('Dossier de configuration accessible à un autre utilisateur')


def write_json(path, data):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False, encoding='utf-8') as f:
        temp = Path(f.name)
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def lock(root):
    secure_state(root)
    fd = os.open(root / 'lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise audit.AuditError('Une autre exécution est en cours') from None
        yield
    finally:
        os.close(fd)


def code_digest():
    paths = [Path(__file__), Path(audit.__file__), Path(keychain.__file__)]
    return hashlib.sha256(b''.join(p.read_bytes() for p in paths)).hexdigest()


def connect(password):
    client = imaplib.IMAP4_SSL('mail.gandi.net', 993, ssl_context=ssl.create_default_context(), timeout=30)
    try:
        audit.checked(client.login('solution@jalauris.fr', password))
        caps = set(b' '.join(audit.checked(client.capability())).upper().split())
        if not {b'UIDPLUS', b'CONDSTORE', b'ENABLE'} <= caps:
            raise audit.AuditError('Gandi doit annoncer UIDPLUS, CONDSTORE et ENABLE ; suppression refusée')
        client.capabilities = tuple(cap.decode('ascii') for cap in caps)
        audit.checked(client.enable('CONDSTORE'))
        return client
    except Exception:
        try:
            client.logout()
        except Exception:
            pass
        raise


def folder_states(client):
    folders = audit.folders_from_list(audit.checked(client.list('""', '*')))
    result = {}
    for folder in folders:
        if folder in result:
            raise audit.AuditError('Dossier IMAP dupliqué')
        response = audit.checked(client.status(quote(folder), '(UIDVALIDITY UIDNEXT MESSAGES HIGHESTMODSEQ)'))
        if len(response) != 1 or not isinstance(response[0], bytes):
            raise audit.AuditError('État des dossiers incomplet')
        tail = re.search(rb'\(([^()]*)\)\s*$', response[0])
        if not tail:
            raise audit.AuditError('État des dossiers illisible')
        tokens = tail[1].split()
        if len(tokens) != 8:
            raise audit.AuditError('État des dossiers incomplet')
        values = dict(zip(tokens[::2], tokens[1::2]))
        expected = {b'UIDVALIDITY', b'UIDNEXT', b'MESSAGES', b'HIGHESTMODSEQ'}
        if set(values) != expected or any(not v.isdigit() for v in values.values()) or int(values[b'HIGHESTMODSEQ']) == 0:
            raise audit.AuditError('Suivi des modifications de dossier indisponible')
        result[folder] = {k.decode(): int(v) for k, v in values.items()}
    return result


def snapshot(client):
    before = folder_states(client)
    messages = audit.scan(client, CANDIDATE, SENT, audit.OWN, 10000, strict=True)
    after = folder_states(client)
    if before != after:
        raise audit.AuditError('Messagerie modifiée pendant la lecture ; aucune nouvelle suppression')
    return messages, after


def deletion_plan(messages, now):
    groups = audit.review(messages, CANDIDATE, SENT, now)
    by_location = {(m['folder'], m['uidvalidity'], m['uid']): m for m in messages}
    candidates, blocked = [], 0
    for group in groups:
        members = [by_location[(m['folder'], m['uidvalidity'], m['uid'])] for m in group['messages']]
        # Sent/other copies must first be classified manually in the closed folder.
        if group['reasons'] or any(m['folder'] != CANDIDATE or m.get('reviewed_non_contact') or m.get('issues') or any(f.lower() in ('\\flagged', '\\deleted', '\\draft') for f in m.get('flags', [])) for m in members):
            blocked += 1
            continue
        candidates.extend(members)
    if len(candidates) > MAX_BATCH:
        raise audit.AuditError('Plafond de 20 messages dépassé ; revue manuelle requise')
    return candidates, blocked


def select_write(client, folder, validity):
    audit.checked(client.select(quote(folder), readonly=False))
    response = client.response('UIDVALIDITY')[1]
    if response != [str(validity).encode()]:
        raise audit.AuditError('UIDVALIDITY modifié ; suppression refusée')


def current_uids(client):
    response = audit.checked(client.uid('SEARCH', None, 'ALL'))
    if len(response) != 1 or not isinstance(response[0], bytes):
        raise audit.AuditError('Inventaire UID incomplet')
    return set(response[0].decode('ascii').split())


def conditional_delete(client, folder, validity, uids, modseq, after_mark):
    """Called only after a fresh, validated snapshot and durable pending journal.

    On a failure the caller retains that journal and blocks every subsequent run.
    Never CLOSE or global EXPUNGE. Best-effort unmark only this initially unmarked batch.
    """
    target = uidset(uids)
    if not isinstance(modseq, int) or modseq <= 0:
        raise audit.AuditError('Révision IMAP invalide')
    select_write(client, folder, validity)
    if not set(uids) <= current_uids(client):
        raise audit.AuditError('Message cible déplacé ou supprimé')
    marked = False
    expunge_started = False
    try:
        client.response('MODIFIED')  # discard earlier response codes
        marked = True  # even a disconnect during STORE may have applied flags
        audit.checked(client.uid('STORE', target, '(UNCHANGEDSINCE %d) +FLAGS.SILENT' % modseq, '(\\Deleted)'))
        modified = client.response('MODIFIED')[1]
        if modified and any(modified):
            raise audit.AuditError('Messages modifiés pendant le traitement')
        after_mark()
        select_write(client, folder, validity)
        expunge_started = True
        audit.checked(client.uid('EXPUNGE', target))
        if set(uids) & current_uids(client):
            raise audit.AuditError('Effacement ciblé non confirmé')
    except Exception:
        if marked and not expunge_started:
            try:
                select_write(client, folder, validity)
                client.uid('STORE', target, '-FLAGS.SILENT', '(\\Deleted)')
            except Exception:
                pass
        raise


def equivalent_after_mark(before, after, targets):
    def indexed(messages):
        return {(m['folder'], m['uidvalidity'], m['uid']): m for m in messages}
    left, right = indexed(before), indexed(after)
    if left.keys() != right.keys():
        return False
    for location, old in left.items():
        new = right[location]
        expected = dict(old)
        if location in targets:
            expected['flags'] = sorted(old['flags'] + ['\\Deleted'])
            expected['modseq'] = new['modseq']
            if new['modseq'] <= old['modseq']:
                return False
        if expected != new:
            return False
    return True


def execute(client, config, root, apply=False):
    if (root / 'pending.json').exists():
        raise audit.AuditError('Opération précédente à vérifier ; relance automatique bloquée')
    first, states = snapshot(client)
    if CANDIDATE not in states or states[CANDIDATE]['UIDVALIDITY'] != config['candidate_uidvalidity']:
        raise audit.AuditError('Dossier sans suite recréé ou remplacé ; reconfiguration nécessaire')
    planned_at = utcnow()
    targets, blocked = deletion_plan(first, planned_at)
    eligible_locations = {(m['folder'], m['uidvalidity'], m['uid']) for m in targets}
    overdue_blocked = sum(1 for group in audit.review(first, CANDIDATE, SENT, planned_at)
                          if datetime.fromisoformat(group['due']) <= planned_at
                          and not any((m['folder'], m['uidvalidity'], m['uid']) in eligible_locations for m in group['messages']))
    summary = {'mode': 'suppression_ciblee' if apply else 'simulation', 'scanned_messages': len(first), 'eligible_messages': len(targets), 'blocked_groups': blocked, 'overdue_blocked_groups': overdue_blocked, 'deleted_messages': 0}
    if not apply or not targets:
        return summary
    # No use of an old audit report: two complete identical inventories in this session.
    second, second_states = snapshot(client)
    if first != second or states != second_states or utcnow() < planned_at:
        raise audit.AuditError('Inventaire ou horloge modifié avant suppression')
    target_locations = {(m['folder'], m['uidvalidity'], m['uid']) for m in targets}
    write_json(root / 'pending.json', {'started_at': utcnow().isoformat(), 'targets': [dict(folder=m['folder'], uidvalidity=m['uidvalidity'], uid=m['uid'], fingerprint=m['fingerprint']) for m in targets]})
    if folder_states(client) != states:
        raise audit.AuditError('Messagerie modifiée avant marquage')

    def after_mark():
        marked_messages, marked_states = snapshot(client)
        if not equivalent_after_mark(first, marked_messages, target_locations):
            raise audit.AuditError('Messagerie modifiée après marquage ; effacement annulé')
        # Other folder states, and candidate cardinality/identity, must stay unchanged.
        for name, state in states.items():
            keys = ('UIDVALIDITY', 'UIDNEXT', 'MESSAGES') if name == CANDIDATE else state.keys()
            if any(marked_states[name][k] != state[k] for k in keys):
                raise audit.AuditError('Dossier modifié après marquage')
        if folder_states(client) != marked_states or utcnow() < planned_at:
            raise audit.AuditError('Messagerie ou horloge modifiée avant effacement')

    conditional_delete(client, CANDIDATE, config['candidate_uidvalidity'], [m['uid'] for m in targets], states[CANDIDATE]['HIGHESTMODSEQ'], after_mark)
    summary['deleted_messages'] = len(targets)
    # Verify removal globally before considering the journal complete.
    final, _ = snapshot(client)
    survivors = {(m['folder'], m['uidvalidity'], m['uid']) for m in final}
    if target_locations & survivors:
        raise audit.AuditError('Effacement non confirmé par le contrôle final')
    write_json(root / 'last-operation.json', {'completed_at': utcnow().isoformat(), 'deleted_messages': len(targets)})
    (root / 'pending.json').unlink()
    return summary


def live_self_test(client):
    """Only our fresh synthetic mailbox: verifies targeted deletion keeps a sentinel."""
    folder = 'JALAURIS-retention-test-' + uuid.uuid4().hex
    audit.checked(client.create(quote(folder)))
    date = utcnow()
    for n in (1, 2):
        body = ('From: solution@jalauris.fr\r\nTo: solution@jalauris.fr\r\nDate: ' + format_datetime(date) + '\r\nMessage-ID: <' + uuid.uuid4().hex + '@jalauris.invalid>\r\nSubject: Test technique retention ' + str(n) + '\r\n\r\nMessage fictif cree pour verifier une suppression ciblee.\r\n').encode()
        audit.checked(client.append(quote(folder), '(\\Deleted)' if n == 2 else None, imaplib.Time2Internaldate(date), body))
    state = folder_states(client)[folder]
    select_write(client, folder, state['UIDVALIDITY'])
    uids = sorted(current_uids(client), key=int)
    if len(uids) != 2:
        raise audit.AuditError('Dossier de test inattendu ; contrôle manuel requis')
    def check_sentinel():
        select_write(client, folder, state['UIDVALIDITY'])
        if current_uids(client) != set(uids):
            raise audit.AuditError('Dossier de test modifié')
    conditional_delete(client, folder, state['UIDVALIDITY'], [uids[0]], state['HIGHESTMODSEQ'], check_sentinel)
    if current_uids(client) != {uids[1]}:
        raise audit.AuditError('Test UID EXPUNGE échoué ; activation refusée')
    # Sentinel was marked by this test only; remove just this known UID.
    audit.checked(client.uid('EXPUNGE', uids[1]))
    if current_uids(client):
        raise audit.AuditError('Nettoyage du test incomplet')
    audit.checked(client.select('INBOX', readonly=True))
    audit.checked(client.delete(quote(folder)))


def record_status(root, result):
    result = dict(result, checked_at=utcnow().isoformat())
    write_json(root / 'status.json', result)
    # Keep only the last 30 days of minimal counters, never addresses or subjects.
    path = root / 'history.json'
    history = json.loads(path.read_text()) if path.exists() else []
    history = [v for v in history if (utcnow() - datetime.fromisoformat(v['checked_at'])).total_seconds() <= 30 * 86400]
    write_json(path, (history + [result])[-100:])


def configure(root):
    if (root / 'pending.json').exists():
        raise audit.AuditError('Opération précédente à résoudre avant toute configuration')
    # Configuration is disabled first, even when renewing a password.
    write_json(root / 'config.json', {'enabled': False})
    print('Configuration : seul le dossier « Demandes sans suite » sera supprimable après 12 mois.')
    print('Les réponses doivent être classées avec la demande close ; toute copie liée dans un autre dossier protège la conversation.')
    print('Tous les échanges doivent rester dans Gandi. Un dossier client, un litige ou un échange repris doit sortir du dossier sans suite.')
    print('Test : création puis suppression de deux messages fictifs dans un dossier temporaire ; aucun envoi de courriel.')
    password = getpass.getpass('Mot de passe IMAP Gandi (non affiché) : ')
    with connect(password) as client:
        messages, states = snapshot(client)
        if any(name.startswith('JALAURIS-retention-test-') for name in states):
            raise audit.AuditError('Un ancien test doit être vérifié avant activation')
        live_self_test(client)
        config = {'enabled': False, 'candidate_uidvalidity': states[CANDIDATE]['UIDVALIDITY'], 'self_test_at': utcnow().isoformat(), 'all_exchanges_in_gandi': True, 'code_digest': code_digest()}
        simulation = execute(client, config, root)
    keychain.save(password)
    del password
    # Confirm background access without an interactive macOS prompt.
    secret = keychain.read(interactive=False)
    with connect(secret):
        pass
    del secret
    config['enabled'] = True
    write_json(root / 'config.json', config)
    record_status(root, dict(simulation, ready=True, live_self_test='passed'))
    print(json.dumps(dict(simulation, ready=True, live_self_test='passed', credential_storage='Trousseau macOS', note='Prêt pour le lancement quotidien. Aucun message réel supprimé pendant la configuration.'), ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['configure', 'simulate', 'run', 'status', 'disable'])
    args = parser.parse_args()
    with lock(STATE):
        if args.command == 'configure':
            configure(STATE)
            return
        path = STATE / 'config.json'
        config = json.loads(path.read_text()) if path.exists() else {'enabled': False}
        if args.command == 'disable':
            config['enabled'] = False
            write_json(path, config)
            print('Suppression désactivée. Mot de passe conservé dans le Trousseau.')
            return
        if args.command == 'status':
            status = json.loads((STATE / 'status.json').read_text()) if (STATE / 'status.json').exists() else {}
            print(json.dumps({'enabled': config.get('enabled', False), 'pending_operation': (STATE / 'pending.json').exists(), 'last_run': status}, ensure_ascii=False, indent=2))
            return
        if not config.get('enabled') or not config.get('all_exchanges_in_gandi') or not config.get('self_test_at'):
            raise audit.AuditError('Configuration locale et test réel nécessaires avant activation')
        if config.get('code_digest') != code_digest():
            raise audit.AuditError('Programme modifié depuis sa validation ; reconfiguration requise')
        password = keychain.read(interactive=False)
        with connect(password) as client:
            del password
            result = execute(client, config, STATE, apply=args.command == 'run')
        record_status(STATE, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Neither raw server exceptions nor credentials ever reach logs/output.
        message = str(error) if isinstance(error, (audit.AuditError, keychain.KeychainError)) else 'Accès Gandi, Trousseau ou stockage local à vérifier'
        try:
            with lock(STATE):
                record_status(STATE, {'error': message, 'pending_operation': (STATE / 'pending.json').exists()})
        except Exception:
            pass
        print('Arrêt de sécurité : ' + message + '. Aucun effacement supplémentaire ; vérifier une éventuelle opération en attente.', file=sys.stderr)
        # Do not claim no mutation occurred: interruption may follow a partial operation.
        sys.exit(1)

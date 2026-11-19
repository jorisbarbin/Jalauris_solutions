#!/usr/bin/env python3
"""Read-only Gandi retention review. No deletion/move/store command exists here."""
import argparse
import calendar
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
import getpass
import imaplib
import json
import os
import re
import ssl
import sys

UTC = timezone.utc
OWN = {'solution@jalauris.fr', 'contact@jalauris.fr', 'rgpd@jalauris.fr', 'solutions@jalauris.fr'}


class AuditError(ValueError):
    """Only fixed, application-owned messages safe to display."""


def anniversary(date):
    year = date.year + 1
    return date.replace(year=year, day=min(date.day, calendar.monthrange(year, date.month)[1]))


def parse_message(folder, validity, uid, metadata, raw, own):
    message = BytesParser(policy=policy.default).parsebytes(raw)
    if message.defects:
        raise AuditError('En-têtes non interprétables')
    internal = re.search(rb'INTERNALDATE "([^"]+)"', metadata)
    if not internal:
        raise AuditError('Date serveur absente')
    server_date = parsedate_to_datetime(internal[1].decode('ascii').replace('-', ' ', 2))
    if server_date.tzinfo is None:
        raise AuditError('Fuseau horaire de la date serveur absent')
    # Read the original value: policy.default may normalize a missing zone to -0000.
    raw_dates = [value for name, value in message.raw_items() if name.lower() == 'date']
    if len(raw_dates) != 1:
        raise AuditError('Date du message absente ou multiple')
    raw_date = raw_dates[0].strip()
    mail_date = parsedate_to_datetime(raw_date)
    if mail_date.tzinfo is None:
        # RFC -0000 is UTC with an unspecified source zone, not a missing time zone.
        # Do not infer UTC for dates with a genuinely absent or unrecognized zone.
        if re.search(r'\s-0000$', raw_date):
            mail_date = mail_date.replace(tzinfo=UTC)
        else:
            raise AuditError('Fuseau horaire du message absent ou non reconnu')
    dates = [server_date, mail_date]
    ids = set(re.findall(r'<[^<>\s]+>', ' '.join(str(message.get(h, '')) for h in ('Message-ID', 'References', 'In-Reply-To'))))
    if not re.fullmatch(r'<[^<>\s]+>', str(message.get('Message-ID', '')).strip()):
        raise AuditError('Message-ID absent ou ambigu')
    addresses = {a.casefold() for _, a in getaddresses([str(message.get(h, '')) for h in ('From', 'To', 'Cc', 'Reply-To')]) if '@' in a}
    return {'folder': folder, 'uidvalidity': validity, 'uid': uid,
            'date': max(d.astimezone(UTC) for d in dates),
            'keys': {'id:'+i for i in ids} | {'address:'+a for a in addresses-own},
            'external': bool(addresses-own)}


def review(messages, candidate, sent, now):
    """Conservative connected components: same external correspondent also links threads."""
    parents = list(range(len(messages)))
    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    seen = {}
    for i, m in enumerate(messages):
        for key in m['keys']:
            if key in seen:
                parents[root(i)] = root(seen[key])
            seen[key] = i
    groups = {}
    for i, m in enumerate(messages):
        groups.setdefault(root(i), []).append(m)
    result = []
    for group in groups.values():
        if not any(m['folder'] == candidate for m in group):
            continue
        last = max(m['date'] for m in group)
        reasons = []
        if any(m['folder'] not in {candidate, *sent} for m in group):
            reasons.append('echange_dans_un_autre_dossier')
        if any(not m['external'] for m in group):
            reasons.append('correspondant_externe_non_identifie')
        if anniversary(last) > now:
            reasons.append('moins_de_12_mois_ou_date_future')
        result.append({'status': 'bloque' if reasons else 'a_verifier_manuellement',
                       'reasons': reasons, 'last_exchange': last.isoformat(),
                       'due': anniversary(last).isoformat(),
                       'messages': [{k: m[k] for k in ('folder', 'uidvalidity', 'uid')} for m in group]})
    return result


def checked(response):
    status, data = response
    if status != 'OK' or data is None:
        raise AuditError('Lecture IMAP incomplète')
    return data


def folders_from_list(lines):
    folders = []
    for line in lines:
        # Unsupported LIST literals/encodings abort; never silently omit a mailbox.
        if not isinstance(line, bytes):
            raise AuditError('Format LIST non pris en charge')
        match = re.fullmatch(rb'\(([^)]*)\) (?:NIL|"(?:[^"\\]|\\.)*") (.+)', line)
        if not match:
            raise AuditError('Format de dossier non pris en charge')
        if b'\\noselect' in match[1].lower().split():
            continue
        name = match[2]
        if name.startswith(b'"') and name.endswith(b'"'):
            name = re.sub(rb'\\(.)', rb'\1', name[1:-1])
        elif name.startswith(b'{'):
            raise AuditError('Nom de dossier littéral non pris en charge')
        folders.append(name.decode('ascii'))
    return folders


def scan(client, candidate, sent, own, limit):
    folders = folders_from_list(checked(client.list('""', '*')))
    if candidate not in folders or not sent or not sent <= set(folders) or candidate in sent:
        raise AuditError('Dossiers sans suite / envoyés à vérifier')
    messages = []
    for folder in folders:
        quoted = '"' + folder.replace('\\', '\\\\').replace('"', '\\"') + '"'
        checked(client.select(quoted, readonly=True))
        validity = client.response('UIDVALIDITY')[1]
        if not validity or not validity[0] or not validity[0].isdigit():
            raise AuditError('UIDVALIDITY absent')
        uids = checked(client.uid('SEARCH', None, 'ALL'))[0].split()
        if len(messages) + len(uids) > limit:
            raise AuditError('Limite de volume dépassée : audit interrompu')
        for uid in uids:
            data = checked(client.uid('FETCH', uid, '(UID INTERNALDATE BODY.PEEK[HEADER.FIELDS (DATE MESSAGE-ID REFERENCES IN-REPLY-TO FROM TO CC REPLY-TO)])'))
            payloads = [v for v in data if isinstance(v, tuple)]
            if len(payloads) != 1:
                raise AuditError('Message disparu ou lecture ambiguë')
            metadata, raw = payloads[0]
            actual = re.search(rb'\bUID (\d+)\b', metadata)
            if not actual or actual[1] != uid:
                raise AuditError('UID incohérent')
            messages.append(parse_message(folder, validity[0].decode(), uid.decode(), metadata, raw, own))
        # Detect changes during a folder scan. The report remains a non-atomic snapshot.
        if checked(client.uid('SEARCH', None, 'ALL'))[0].split() != uids:
            raise AuditError('Dossier modifié pendant la lecture : relancer')
    if folders_from_list(checked(client.list('""', '*'))) != folders:
        raise AuditError('Liste des dossiers modifiée : relancer')
    return messages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list-folders', action='store_true', help='Lister seulement les noms techniques des dossiers, sans lire les messages')
    parser.add_argument('--candidate-folder', help='Nom IMAP exact du dossier classé sans suite')
    parser.add_argument('--sent-folder', action='append', help='Répéter pour chaque dossier envoyé')
    parser.add_argument('--own-address', action='append', default=[], help='Alias supplémentaires de JALAURIS')
    parser.add_argument('--max-messages', type=int, default=10000)
    args = parser.parse_args()
    if not args.list_folders and (not args.candidate_folder or not args.sent_folder):
        parser.error('--candidate-folder et --sent-folder sont nécessaires pour un audit')
    password = os.environ.get('JALAURIS_IMAP_PASSWORD') or getpass.getpass('Mot de passe IMAP Gandi (non affiché) : ')
    stage = 'connexion sécurisée à Gandi'
    try:
        with imaplib.IMAP4_SSL('mail.gandi.net', 993, ssl_context=ssl.create_default_context(), timeout=30) as client:
            stage = 'authentification (identifiant, mot de passe ou accès IMAP à vérifier)'
            checked(client.login('solution@jalauris.fr', password))
            del password
            print('Connexion IMAP et authentification réussies.', file=sys.stderr)
            stage = 'lecture de la liste des dossiers'
            if args.list_folders:
                folders = folders_from_list(checked(client.list('""', '*')))
                print(json.dumps({'mode': 'liste_dossiers_seulement', 'folders': folders}, ensure_ascii=False, indent=2))
                return
            stage = 'lecture des dossiers et des en-têtes (date ou format à vérifier)'
            messages = scan(client, args.candidate_folder, set(args.sent_folder), OWN | {a.casefold() for a in args.own_address}, args.max_messages)
            stage = 'fermeture de la connexion'
    except AuditError:
        raise
    except (ValueError, TypeError, OverflowError, OSError, imaplib.IMAP4.error) as from_error:
        raise AuditError('Échec pendant : ' + stage) from None
    now = datetime.now(UTC)
    print(json.dumps({'mode': 'lecture_seule', 'deletion_enabled': False, 'generated_at': now.isoformat(),
                      'warning': 'Instantané indicatif, jamais une autorisation de suppression. Vérifier les échanges hors IMAP.',
                      'scanned_messages': len(messages), 'groups': review(messages, args.candidate_folder, set(args.sent_folder), now)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except AuditError as error:
        print('Audit interrompu : ' + str(error) + '. Aucun message modifié ; aucun rapport d’audit produit.', file=sys.stderr)
        sys.exit(1)
    except (ValueError, TypeError, OverflowError, OSError, imaplib.IMAP4.error):
        # Do not print server exceptions: they can contain mailbox data or credentials.
        print('Audit interrompu : configuration, accès ou données à vérifier. Aucun message modifié ; aucun rapport partiel.', file=sys.stderr)
        sys.exit(1)

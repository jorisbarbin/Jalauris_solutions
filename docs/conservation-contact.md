# Conservation des contacts — état au 19 novembre 2026

## État vérifié et activation

Le propriétaire a testé l’audit sur la boîte Gandi `solution@jalauris.fr` : connexion réussie, quatre messages examinés, dossier `Demandes sans suite` et dossier envoyé `Sent` confirmés. Il a confirmé que tous les échanges professionnels concernés sont conservés dans cette boîte. Le courriel de bienvenue Gandi sans Message-ID bénéficie d’une exception administrative strictement limitée (voir ci-dessous).

Le test réel des deux messages fictifs a réussi chez Gandi. Le secret est enregistré dans le Trousseau macOS. **La tâche quotidienne est active**, à 9 h chaque jour (Europe/Paris), sous l’identifiant `conservation-des-contacts-jalauris`. Une première exécution effective a réussi le 19 novembre 2026 : 4 messages examinés, 0 éligible, 0 suppression et 0 conversation échue bloquée. La disponibilité quotidienne du Mac, de l’application, du réseau et du Trousseau reste nécessaire. Le mot de passe n’a pas été communiqué dans le chat ni affiché par le programme.

## Organisation de la boîte

- Classer manuellement dans `Demandes sans suite` les conversations closes, sans contrat, sans litige ni obligation particulière de conservation.
- Y déplacer aussi leurs réponses et copies lorsque leur classement « sans suite » est vérifié. Le programme ne supprime **jamais** dans `Sent`, `INBOX`, les archives, la corbeille ou un autre dossier. Toute copie liée qui y reste bloque le nettoyage de la conversation, même si elle est ancienne. Ne pas déplacer des documents nécessaires à un client pour débloquer le programme.
- Les messages marqués d’une étoile/drapeau (`Flagged`), brouillons (`Draft`) ou déjà marqués pour suppression (`Deleted`) sont protégés.
- Retirer du dossier sans suite toute demande réactivée ou à conserver. Conserver tous les nouveaux échanges dans Gandi ; une autre adresse ou un contact téléphonique non documenté ne peut pas être découvert par IMAP.
- Les exceptions clients, pièces comptables, contrats et litiges ont leurs durées propres et doivent être revues. Elles ne justifient pas de conserver indéfiniment toutes les données.

La durée est de 12 mois calendaires après le dernier échange entrant **ou sortant**, en retenant aussi la date serveur si elle est plus récente. Les relances de prospection ne réinitialisent pas pour autant le délai CNIL spécifique à la prospection : ce traitement relève d’une finalité et de règles distinctes.

## Une commande pour configurer sur ce Mac

Depuis la racine du dépôt :

```sh
python3 scripts/contact_retention_cleanup.py configure
```

La commande :

1. Désactive d’abord toute configuration antérieure. Demande le mot de passe sans l’afficher, puis vérifie Gandi avec TLS et certificat validé (`mail.gandi.net:993`).
2. Exige les capacités UIDPLUS, CONDSTORE et ENABLE. Vérifie tous les dossiers et leur suivi des modifications.
3. Crée un dossier temporaire unique `JALAURIS-retention-test-…`, y dépose deux courriels fictifs **sans aucun envoi SMTP**, supprime le premier par UID et vérifie que le second, pourtant déjà marqué pour suppression, est conservé. Elle supprime ensuite uniquement ce second courriel de test et le dossier devenu vide. En cas d’échec, la configuration reste désactivée ; un dossier temporaire peut rester à examiner.
4. Réalise une simulation sur les messages réels, sans les supprimer.
5. Enregistre le secret dans le Trousseau macOS sous le service `fr.jalauris.retention.imap`, compte `solution@jalauris.fr`, puis vérifie l’accès sans invite interactive. Aucun secret dans Git, les arguments de commande, les rapports ou les fichiers publics.
6. Enregistre une configuration locale validée. Elle affiche `ready: true` et `live_self_test: passed` uniquement après succès de toutes ces étapes.

Lors d’une première mise en service, activer ensuite la tâche Codex et vérifier une exécution. Ces deux étapes ont été effectuées le 19 novembre 2026. Le Mac doit être allumé, en ligne, le Trousseau accessible et l’application ouverte. Les permissions locales et réseau restent applicables ; une tâche bloquée n’est pas une tâche exécutée. Ne pas annoncer une purge quotidienne autonome avant cette vérification.

## Commandes utiles

```sh
# Simulation avec le mot de passe déjà dans le Trousseau : aucun effacement
python3 scripts/contact_retention_cleanup.py simulate

# Exécution effective selon toutes les protections, utilisée par la tâche quotidienne
python3 scripts/contact_retention_cleanup.py run

# État et dernier résultat, sans accès aux courriels
python3 scripts/contact_retention_cleanup.py status

# Arrêt immédiat des prochaines suppressions (secret conservé dans le Trousseau)
python3 scripts/contact_retention_cleanup.py disable

# Audit autonome historique, strictement en lecture seule
python3 scripts/contact_retention_audit.py --candidate-folder 'Demandes sans suite' --sent-folder 'Sent'
```

Pour suspendre complètement les passages, mettre aussi la tâche Codex en pause. Pour reprendre après modification du programme, relancer la configuration : une empreinte des trois fichiers exécutables empêche l’utilisation automatique d’un code modifié sans nouvelle validation.

## Protections de la suppression

- Inventaire de tous les dossiers sélectionnables, pas seulement les dossiers abonnés. Lecture des en-têtes avec BODY.PEEK ; pas de corps ni de pièces jointes. Identifiants, références et correspondants (dont Reply-To du formulaire et Bcc) rapprochent les conversations. Le rapprochement par adresse est conservateur : des demandes indépendantes peuvent être bloquées ensemble.
- Deux inventaires complets identiques avant suppression ; comparaison des UIDVALIDITY, UIDNEXT, nombres de messages et HIGHESTMODSEQ de tous les dossiers. Toute lecture incomplète, date ambiguë, en-tête d’adresse ambigu, référence non interprétable ou volume supérieur à 10 000 messages arrête ou bloque le nettoyage.
- Dossier cible lié à son UIDVALIDITY au moment de la configuration. Un dossier recréé n’est jamais accepté silencieusement. Message identifié par dossier, UIDVALIDITY, UID et empreinte des en-têtes.
- Maximum 20 messages par passage. Au-delà, le lot entier est bloqué pour revue ; aucun élargissement automatique du périmètre.
- Verrou local contre les exécutions simultanées. Journal préalable durable avant tout marquage.
- Marquage conditionnel `UID STORE … (UNCHANGEDSINCE …) +FLAGS.SILENT (\Deleted)`. Si le serveur signale une modification concurrente, arrêt sans effacement.
- Nouvel inventaire après marquage : seules les modifications attendues des messages cibles sont acceptées. Puis `UID EXPUNGE` sur les seuls UID validés. **Jamais de commande EXPUNGE globale, CLOSE, purge de corbeille ou effacement par sujet/expéditeur.**
- Contrôle après effacement. Si une panne ou une réponse ambiguë survient, `pending.json` reste présent et interdit toutes les relances automatiques. Avant le début de l’effacement, une tentative de retrait du seul marquage ajouté par le programme est faite si la connexion fonctionne. Après une interruption, certains messages peuvent déjà avoir été effacés ou rester marqués : ne jamais prétendre le contraire.

IMAP ne fournit pas de transaction atomique sur plusieurs dossiers. Une petite fenêtre de concurrence subsiste entre la dernière vérification et l’effacement ; les contrôles réduisent ce risque sans l’annuler. Ne pas déplacer ni reclasser les conversations pendant une opération ; si ce risque résiduel n’est pas acceptable, garder la suppression manuelle ou adopter un suivi de dossiers transactionnel distinct.

## État local, alertes et incidents

Les fichiers d’état sont dans `.jalauris-retention`, **dans le dossier parent du dépôt**, hors des fichiers servis par le site. Dossier accessible uniquement à l’utilisateur (0700), fichiers privés (0600). Les journaux ne contiennent ni sujet, ni adresse de correspondant, ni contenu de message. L’historique garde des compteurs sur 30 jours (100 résultats au maximum). Le journal d’opération en attente conserve les références et empreintes nécessaires à l’analyse, jusqu’à résolution manuelle.

La tâche doit signaler les erreurs, les suppressions effectuées et les conversations échues mais bloquées (`overdue_blocked_groups`). Un message récent bloqué est normal. Une absence d’exécution parce que le Mac est éteint ne génère pas forcément une alerte : consulter les derniers passages dans Codex et `status` ; si une disponibilité continue est nécessaire, choisir ultérieurement un hôte permanent.

En présence de `pending.json` : désactiver les passages, examiner les UID ciblés, les éventuels marqueurs Deleted et l’état effectif du serveur. Ne pas supprimer le journal ni relancer pour « forcer ». La reprise nécessite une résolution humaine documentée. Aucun outil automatique d’effacement de ce journal n’est livré.

Une exécution quotidienne peut dépasser l’échéance de quelques heures et davantage en cas de panne ou de blocage. Elle ne garantit pas l’effacement exact à la seconde des 12 mois. Revoir manuellement les dossiers échus bloqués.

## Exception de bienvenue et dates

Le propriétaire a fourni les en-têtes du message `[GANDI] Bienvenue`, daté du 16 novembre 2026 à 14:41:04 UTC, sans Message-ID. Seule la référence INBOX / UIDVALIDITY `1794840065` / UID `1`, avec les From, To, Subject et Date exacts et sans référence de conversation, Cc, Bcc ni Reply-To, est reconnue comme administrative. Son anomalie reste visible (`reviewed_non_contact: true`). Le message est conservé et ne fait jamais partie des cibles. Un déplacement ou une modification invalide l’exception. Tout autre Message-ID absent ou ambigu bloque l’ensemble des propositions.

Le fuseau explicite `-0000` signifie UTC sans indication du fuseau d’origine ; il est accepté. Un fuseau réellement absent ou inconnu reste bloquant. Les valeurs brutes sont examinées pour éviter qu’une normalisation de bibliothèque masque l’absence de fuseau.

## Prestataires et limites

Le formulaire utilise Resend pour envoyer vers Gandi. **La suppression IMAP ne supprime aucune copie Resend**, sauvegarde Gandi, export local ou copie chez un destinataire. Vérifier séparément les offres, contrats et délais de ces prestataires. La documentation Resend consultée annonce 30 jours pour e-mails et journaux Free/Pro/Scale, des modalités Enterprise spécifiques et aucune API d’effacement d’un e-mail individuel. L’offre souscrite reste à vérifier.

## Vérification et sources

`python3 -m unittest discover -s tests -v`

Les tests couvrent les réponses récentes, dossiers protégés, drapeaux, dates, identifiants, plafond, changement d’inventaire, conflit de marquage, panne, verrou, protection du journal, test temporaire, configuration désactivée et compatibilité de la commande conditionnelle avec imaplib. Les essais simulés ne remplacent pas le test réel effectué par `configure`.

Sources consultées le 19 novembre 2026 :

- [CNIL — durée selon la finalité](https://www.cnil.fr/fr/cnil-direct/question/dois-je-fixer-une-duree-de-conservation-des-donnees-dans-mon-fichier)
- [CNIL — clients et prospects](https://www.cnil.fr/fr/questions-reponses-sur-les-referentiels-relatifs-la-gestion-des-activites-commerciales-et-des)
- [Gandi — paramètres IMAP](https://docs.gandi.net/en/gandimail/standard_email_settings/)
- [RFC 4315 — UID EXPUNGE ciblé](https://www.rfc-editor.org/rfc/rfc4315.html#section-2.1)
- [RFC 7162 — CONDSTORE et modifications concurrentes](https://www.rfc-editor.org/rfc/rfc7162.html)
- [Python — dates et fuseau -0000](https://docs.python.org/3/library/email.utils.html#email.utils.parsedate_to_datetime)
- [Resend — rétention et effacement](https://resend.com/security/gdpr)
- [OpenAI — tâches planifiées et exigences d’exécution locale](https://learn.chatgpt.com/docs/automations?surface=app)

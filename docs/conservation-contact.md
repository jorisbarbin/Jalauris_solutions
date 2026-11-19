# Conservation des demandes de contact — 19 novembre 2026

## État réel

L’envoi du formulaire passe par Resend vers solution@jalauris.fr, hébergée chez Gandi (confirmation du propriétaire). Le site n’enregistre pas les demandes dans une base dédiée. L’accès IMAP n’a pas été vérifié et aucun identifiant n’a été fourni. **Aucune suppression, aucun déplacement et aucune tâche planifiée ne sont activés.** Un audit IMAP en lecture seule est livré et testé avec des données fictives ; il n’a pas été exécuté sur la boîte réelle.

## Règles retenues

- Demandes classées sans suite : échéance à 12 mois calendaires après le dernier échange entrant OU sortant. Le délai n’est pas calculé depuis le seul premier formulaire.
- Clients, devis encore actifs, litiges, obligations légales et besoins de preuve documentés : hors purge générale. Prévoir une durée spécifique et une révision de l’exception ; ne pas les conserver indéfiniment par défaut.
- La prospection éventuelle obéit à ses propres règles ; le repère CNIL de trois ans depuis le dernier contact venant du prospect n’est ni une permission de prospecter, ni une raison d’allonger automatiquement les demandes sans suite.
- Le classement « sans suite » est une décision humaine, jamais un filtre sur le seul sujet `[JALAURIS]` ou l’expéditeur `contact@jalauris.fr` (commun à tous les formulaires).

Les 12 mois sont une politique de JALAURIS proportionnée à sa finalité, non une durée universelle imposée par la CNIL. Dans l’attente de l’automatisation, examiner les échéances au moins chaque semaine et traiter les demandes échues ; une exécution quotidienne future réduira le dépassement technique à environ un jour, hors panne. Ne pas prétendre garantir exactement 12 mois avec une purge mensuelle.

## Préparation Gandi

1. Vérifier l’activation IMAP dans les paramètres Gandi ; serveur `mail.gandi.net`, port `993`, TLS avec validation du certificat, identifiant complet `solution@jalauris.fr`.
2. Identifier tous les dossiers réels : réception, envoyés de chaque logiciel/appareil, archives, clients, devis, corbeille, indésirables, sous-dossiers. Vérifier les messages envoyés conservés uniquement en local, les autres boîtes et les transferts.
3. Créer manuellement un dossier dédié, par exemple `Demandes sans suite`, et y classer uniquement les demandes closes sans obligation de conservation. Les réponses peuvent rester dans les dossiers envoyés examinés par l’audit.
4. Documenter les alias d’envoi JALAURIS. Ne jamais communiquer le mot de passe dans un chat, un commit ou un argument de commande. Le script le demande sans l’afficher, ou accepte `JALAURIS_IMAP_PASSWORD` injecté par un gestionnaire de secrets.

## Audit livré (Python 3.10+)

Depuis la racine du dépôt, après vérification des noms IMAP exacts :

```sh
python3 scripts/contact_retention_audit.py --candidate-folder 'Demandes sans suite' --sent-folder 'Sent'
```

`Sent` est un exemple, pas un nom confirmé chez Gandi. Répéter `--sent-folder` pour tous les dossiers envoyés et `--own-address` pour les alias supplémentaires. Les noms internationaux doivent utiliser leur représentation IMAP modified UTF-7 ; un format non reconnu interrompt l’audit plutôt que d’omettre le dossier.

Le script énumère tous les dossiers sélectionnables (pas seulement les abonnements), ouvre en lecture seule et ne récupère que les en-têtes avec `BODY.PEEK`, sans marquer les messages comme lus. Il rapproche les identifiants `Message-ID`, `References`, `In-Reply-To` et les adresses externes, notamment `Reply-To` du formulaire. Le rapprochement par correspondant est volontairement conservateur : plusieurs demandes indépendantes peuvent être bloquées ensemble. Il retient la plus récente des dates de message et de serveur, puis celle de tous les échanges liés. Un message lié dans tout autre dossier que « sans suite » ou les dossiers envoyés bloque la proposition (y compris corbeille et archives).

Une date, un identifiant ou une lecture incomplets, un dossier absent, un changement détecté ou un volume supérieur à 10 000 messages arrêtent l’audit sans rapport partiel. Les en-têtes et adresses restent en mémoire. La sortie contient des compteurs, dates et références dossier/UID/UIDVALIDITY, jamais le corps, le sujet ou les adresses. Ces références restent des données à accès restreint. Si le rapport doit être enregistré, le stocker hors du dossier servi par Vercel, avec permissions limitées, et l’effacer après revue (au plus 30 jours).

**Le rapport est un instantané indicatif, non atomique, jamais un manifeste de suppression.** Il ne voit pas les réponses hors IMAP, les échanges téléphoniques, les nouvelles adresses non reliées, les archives locales ni les données Resend. Les propositions `a_verifier_manuellement` doivent être contrôlées. Il n’existe pas d’option `--apply`.

Tests : `python3 -m unittest discover -s tests -v`.

## Mécanisme de suppression à réaliser après validation IMAP

Une automatisation fiable est techniquement envisageable, mais son volet destructif ne peut pas être validé sans la boîte et son organisation réelle. Conditions de mise en service :

1. Auditer la boîte réelle et un dossier de test avec réponses récentes, copies dans plusieurs dossiers, messages sans références, clients, changements d’UIDVALIDITY et erreurs réseau. Confirmer le suivi des échanges hors messagerie.
2. Utiliser un registre privé de dossiers de contact : statut humain « clos sans suite », date du dernier échange, exceptions motivées avec échéance de révision, liste exacte des copies admissibles. Prévenir les faux rapprochements et les changements d’adresse.
3. Faire une revue avant échéance (par exemple à 11 mois) et retirer immédiatement tout dossier réactivé du périmètre. Une quarantaine supplémentaire après 12 mois prolongerait la conservation : ne pas l’ajouter implicitement.
4. Exécuter quotidiennement sur un hôte privé durable, avec secret protégé, verrou contre les exécutions simultanées, plafond par lot, alerte en cas d’échec et journal minimal sans contenu/adresses. Préférer ce service à une route HTTP publique de purge.
5. Avant toute suppression, refaire un inventaire complet et vérifier dernier échange, statut, exclusions, UIDVALIDITY, UID et Message-ID. Arrêter tout le lot en cas de doute ou d’inventaire incomplet. Un rapport ancien ne suffit pas.
6. Vérifier le support serveur d’UIDPLUS et de `UID EXPUNGE` ciblé sur les seuls UID approuvés. **Ne jamais utiliser `EXPUNGE` global**, qui supprimerait aussi d’autres messages déjà marqués. Sans cette capacité vérifiée, rester en procédure manuelle. Ne pas considérer un simple déplacement dans la corbeille comme un effacement définitif.
7. Inclure explicitement les réponses et copies admissibles dans les dossiers envoyés, tout en préservant les pièces nécessaires aux clients, contrats et litiges. Recontrôler après opération, gérer les suppressions partielles et les relances de façon idempotente.

## Prestataires et copies hors périmètre

Une suppression IMAP ne supprime ni les copies Resend, ni les sauvegardes Gandi, ni les exports locaux ou les copies chez les destinataires. Vérifier séparément les durées contractuelles, sauvegardes et demandes d’effacement avec chaque prestataire. La documentation Resend consultée indique 30 jours pour e-mails et journaux des offres Free/Pro/Scale, des modalités spécifiques Enterprise et l’absence d’API de suppression d’un e-mail individuel. L’offre réellement souscrite reste à vérifier ; aucun effacement Resend n’est implémenté ou revendiqué ici.

## Sources officielles consultées le 19 novembre 2026

- [CNIL — fixer la durée selon la finalité](https://www.cnil.fr/fr/cnil-direct/question/dois-je-fixer-une-duree-de-conservation-des-donnees-dans-mon-fichier)
- [CNIL — référentiel activités commerciales et prospects](https://www.cnil.fr/fr/questions-reponses-sur-les-referentiels-relatifs-la-gestion-des-activites-commerciales-et-des)
- [Gandi — paramètres IMAP](https://docs.gandi.net/en/gandimail/standard_email_settings/)
- [Python — imaplib, lecture seule et commandes UID](https://docs.python.org/3/library/imaplib.html)
- [Resend — rétention et effacement](https://resend.com/security/gdpr)

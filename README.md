# JALAURIS Solutions

Site vitrine statique, avec formulaire serveur Vercel (`api/contact.js`), protection Cloudflare Turnstile et envoi Resend. Branche de référence : `main`.

Pour prévisualiser les pages : `python3 -m http.server 8000`. Ce serveur local ne fait pas fonctionner les routes Vercel du formulaire.

## Informations légales et confidentialité

- `mentions-legales.html` : page distincte, identité confirmée par le propriétaire et données recoupées avec l’Annuaire des Entreprises. Restent à compléter : RCS/greffe, gérant, direction de publication, téléphone de l’entreprise et de Vercel, rédaction si applicable. Aucun nom de dirigeant ou greffe n’a été déduit du compte GitHub ou de l’adresse.
- `politique-confidentialite.html` : politique RGPD séparée, conservation de 12 mois après le dernier échange des demandes sans suite, distinction des copies prestataires. L’automatisation de suppression n’est pas active.
- `docs/conservation-contact.md` : étude, préparation Gandi, règles, limites, sources et conditions de mise en service.
- `scripts/contact_retention_audit.py` : audit IMAP strictement en lecture seule ; aucun effacement ou déplacement.
- `scripts/contact_retention_cleanup.py` : suppression ciblée, avec configuration locale, test réel obligatoire et secret dans le Trousseau macOS. La tâche quotidienne est préparée à 9 h (Paris), en pause jusqu’à la configuration.

Pour terminer la configuration : `python3 scripts/contact_retention_cleanup.py configure`. Cette étape teste deux messages fictifs dans un dossier temporaire sans envoyer de courriel ni supprimer de message réel. Voir la procédure et les limites dans `docs/conservation-contact.md`.

Les champs à compléter signifient que les mentions légales ne sont pas encore finalisées. Vérifier les obligations supplémentaires si l’activité évolue (vente aux consommateurs, activité réglementée, etc.).

## Vérification

`python3 -m unittest discover -s tests -v`

Les tests automatisés utilisent des données fictives ; le test réel de mise en service se fait localement avec la commande `configure`. Ne pas stocker de secrets ou de rapports de messagerie dans le dépôt ou dans les fichiers publics du site.

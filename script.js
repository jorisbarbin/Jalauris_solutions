const menuButton = document.querySelector('.menu-toggle');
const nav = document.querySelector('.nav');
menuButton?.addEventListener('click', () => {
  const opened = nav.classList.toggle('open');
  menuButton.setAttribute('aria-expanded', String(opened));
  menuButton.setAttribute('aria-label', opened ? 'Fermer le menu' : 'Ouvrir le menu');
});
nav?.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
  nav.classList.remove('open');
  menuButton?.setAttribute('aria-expanded', 'false');
  menuButton?.setAttribute('aria-label', 'Ouvrir le menu');
}));
document.getElementById('year').textContent = new Date().getFullYear();
menuButton?.addEventListener('keydown', event => {
  if (event.key === 'Escape') { nav?.classList.remove('open'); menuButton.setAttribute('aria-expanded', 'false'); menuButton.setAttribute('aria-label', 'Ouvrir le menu'); }
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && nav?.classList.contains('open')) { nav.classList.remove('open'); menuButton?.setAttribute('aria-expanded', 'false'); menuButton?.setAttribute('aria-label', 'Ouvrir le menu'); menuButton?.focus(); }
});
// Remplacer cette adresse avant la mise en ligne par une adresse professionnelle vérifiée.
const CONTACT_EMAIL = 'CONTACT_EMAIL_A_CONFIGURER';
document.getElementById('contact-form')?.addEventListener('submit', e => {
  e.preventDefault();
  const form = e.currentTarget;
  if (!form.reportValidity()) return;
  const helper = document.getElementById('form-helper');
  if (CONTACT_EMAIL === 'CONTACT_EMAIL_A_CONFIGURER') {
    helper.textContent = 'La destination du formulaire doit être configurée avant utilisation. Renseignez CONTACT_EMAIL dans script.js.';
    helper.setAttribute('role', 'alert');
    return;
  }
  const data = new FormData(form);
  const value = key => String(data.get(key) || '').trim();
  const subject = `Projet JALAURIS — ${value('besoin')}`;
  const body = `Bonjour,\n\nJe souhaite vous présenter un projet.\n\nNom : ${value('nom')}\nEntreprise : ${value('entreprise')}\nE-mail : ${value('email')}\nBesoin : ${value('besoin')}\n\nDescription :\n${value('message')}\n`;
  window.location.href = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
});

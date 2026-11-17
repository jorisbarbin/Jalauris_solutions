const menuButton = document.querySelector('.menu-toggle');
const nav = document.querySelector('.navigation');
function closeMenu() {
  nav?.classList.remove('open');
  menuButton?.setAttribute('aria-expanded', 'false');
  menuButton?.setAttribute('aria-label', 'Ouvrir le menu');
}
menuButton?.addEventListener('click', () => {
  const open = nav.classList.toggle('open');
  menuButton.setAttribute('aria-expanded', String(open));
  menuButton.setAttribute('aria-label', open ? 'Fermer le menu' : 'Ouvrir le menu');
});
nav?.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && nav?.classList.contains('open')) { closeMenu(); menuButton?.focus(); }
});
document.getElementById('year').textContent = String(new Date().getFullYear());

// À configurer avant toute utilisation commerciale du formulaire.
const CONTACT_EMAIL = 'solution@jalauris.fr';
document.getElementById('contact-form')?.addEventListener('submit', e => {
  e.preventDefault();
  const form = e.currentTarget;
  if (!form.reportValidity()) return;
  const helper = document.getElementById('form-helper');

  const data = new FormData(form);
  const get = key => String(data.get(key) || '').trim();
  const subject = 'Projet JALAURIS — ' + get('besoin');
  const body = 'Bonjour,\n\nJe souhaite vous présenter un projet.\n\nNom : ' + get('nom') +
    '\nEntreprise : ' + get('entreprise') + '\nEmail : ' + get('email') +
    '\nBesoin : ' + get('besoin') + '\n\nDescription :\n' + get('message');
  window.location.href = 'mailto:' + CONTACT_EMAIL + '?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(body);
});

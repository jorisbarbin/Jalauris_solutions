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
const year = document.getElementById('year');
if (year) year.textContent = String(new Date().getFullYear());

const form = document.getElementById('contact-form');
const helper = document.getElementById('form-helper');
const submit = document.getElementById('submit-contact');
let turnstileId = null;
let turnstileToken = '';
let isSending = false;

function feedback(message) { if (helper) helper.textContent = message; }
async function startContact() {
  if (!form || !submit) return;
  try {
    const configResponse = await fetch('/api/contact-config', { cache: 'no-store' });
    if (!configResponse.ok) throw new Error('Configuration indisponible');
    const config = await configResponse.json();
    if (!config.configured || !config.siteKey) {
      feedback('Le formulaire sera disponible prochainement. Merci de votre compréhension.');
      return;
    }
    // Le script Turnstile est chargé de manière asynchrone : patienter sans bloquer l’interface.
    let attempts = 0;
    while (!window.turnstile && attempts++ < 60) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    if (!window.turnstile) throw new Error('Vérification anti-robots indisponible');
    turnstileId = window.turnstile.render('#turnstile-widget', {
      sitekey: config.siteKey,
      callback: token => { turnstileToken = token; },
      'expired-callback': () => { turnstileToken = ''; },
      'error-callback': () => { turnstileToken = ''; feedback('La vérification anti-robots a échoué. Réessayez.'); }
    });
    submit.disabled = false;
    submit.firstChild.textContent = 'Envoyer ma demande ';
    feedback('Votre message sera transmis directement à JALAURIS. Les informations ne sont utilisées que pour répondre à votre demande.');
  } catch (error) {
    feedback('Le formulaire est momentanément indisponible. Merci de réessayer plus tard.');
  }
}
form?.addEventListener('submit', async event => {
  event.preventDefault();
  if (isSending || !form.reportValidity()) return;
  if (!turnstileToken) { feedback('Veuillez valider la protection anti-robots.'); return; }
  const data = new FormData(form);
  const payload = Object.fromEntries(data.entries());
  payload.turnstileToken = turnstileToken;
  isSending = true;
  submit.disabled = true;
  feedback('Envoi de votre demande…');
  try {
    const response = await fetch('/api/contact', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || 'L’envoi a échoué.');
    form.reset();
    feedback('Votre demande a bien été envoyée. Nous vous répondrons dès que possible.');
  } catch (error) {
    feedback(error.message || 'L’envoi a échoué. Merci de réessayer.');
  } finally {
    isSending = false;
    turnstileToken = '';
    if (window.turnstile && turnstileId !== null) window.turnstile.reset(turnstileId);
    submit.disabled = false;
  }
});
startContact();

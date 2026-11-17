const ALLOWED_NEEDS = ['Conception de logiciel sur mesure', 'Prestations informatiques', 'Conseil en gestion', 'Vente de logiciels', 'Autre demande'];
const json = (res, status, message) => res.status(status).json({ message });
const clean = (value, limit) => typeof value === 'string' ? value.trim().slice(0, limit) : '';
const escapeHtml = value => value.replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'POST') return json(res, 405, 'Méthode non autorisée.');
  if (!process.env.TURNSTILE_SECRET_KEY || !process.env.RESEND_API_KEY || !process.env.CONTACT_TO_EMAIL || !process.env.CONTACT_FROM_EMAIL) {
    return json(res, 503, 'Le formulaire n’est pas encore disponible.');
  }
  const payload = req.body && typeof req.body === 'object' ? req.body : {};
  const nom = clean(payload.nom, 100), entreprise = clean(payload.entreprise, 120),
    email = clean(payload.email, 200), besoin = clean(payload.besoin, 100),
    message = clean(payload.message, 4000), token = clean(payload.turnstileToken, 2048);
  if (!nom || !message || !email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || !ALLOWED_NEEDS.includes(besoin) || !token) {
    return json(res, 400, 'Veuillez vérifier les champs et la protection anti-robots.');
  }
  try {
    const verify = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
      method: 'POST',
      headers: {'content-type':'application/x-www-form-urlencoded'},
      body: new URLSearchParams({secret: process.env.TURNSTILE_SECRET_KEY, response: token})
    });
    if (!verify.ok) return json(res, 502, 'Service de vérification indisponible.');
    const result = await verify.json();
    if (!result.success || (result.hostname && !['jalaurissolutions.vercel.app','jalauris.fr','www.jalauris.fr'].includes(result.hostname))) {
      return json(res, 400, 'Vérification anti-robots refusée. Veuillez réessayer.');
    }
    const lines = ['Nouvelle demande depuis JALAURIS Solutions', '', 'Nom : '+nom, 'Entreprise : '+entreprise, 'Email : '+email, 'Besoin : '+besoin, '', 'Message :', message];
    const mail = await fetch('https://api.resend.com/emails', {
      method:'POST',
      headers:{'Authorization':'Bearer '+process.env.RESEND_API_KEY,'Content-Type':'application/json'},
      body:JSON.stringify({
        from:process.env.CONTACT_FROM_EMAIL,
        to:[process.env.CONTACT_TO_EMAIL],
        reply_to:email,
        subject:'[JALAURIS] '+besoin,
        text:lines.join('\n'),
        html:'<pre style="white-space:pre-wrap;font-family:sans-serif">'+escapeHtml(lines.join('\n'))+'</pre>'
      })
    });
    if (!mail.ok) { console.error('Envoi Resend refusé :',mail.status); return json(res, 502, 'Impossible d’envoyer le message actuellement.'); }
    return json(res, 200, 'Votre demande a bien été envoyée.');
  } catch (err) {
    console.error('Contact error:',err instanceof Error ? err.message : 'unknown');
    return json(res, 502, 'Le service de contact est momentanément indisponible.');
  }
}

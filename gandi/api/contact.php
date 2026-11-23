<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

function reply(int $status, string $message): never {
    http_response_code($status);
    echo json_encode(['message' => $message], JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}
function field(array $payload, string $name, int $max): string {
    $value = $payload[$name] ?? '';
    if (!is_string($value)) return '';
    return trim(mb_substr($value, 0, $max, 'UTF-8'));
}
function postJson(string $url, array $payload, array $headers = []): ?array {
    $handle = curl_init($url);
    if ($handle === false) return null;
    curl_setopt_array($handle, [
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE),
        CURLOPT_HTTPHEADER => array_merge(['Content-Type: application/json'], $headers),
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CONNECTTIMEOUT => 5,
        CURLOPT_TIMEOUT => 15,
        CURLOPT_FOLLOWLOCATION => false,
    ]);
    $body = curl_exec($handle);
    $code = (int) curl_getinfo($handle, CURLINFO_HTTP_CODE);
    curl_close($handle);
    if (!is_string($body)) return null;
    return ['status' => $code, 'data' => json_decode($body, true)];
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    header('Allow: POST');
    reply(405, 'Méthode non autorisée.');
}

foreach (['TURNSTILE_SECRET_KEY', 'RESEND_API_KEY', 'CONTACT_FROM_EMAIL', 'CONTACT_TO_EMAIL'] as $name) {
    if (trim((string) getenv($name)) === '') {
        reply(503, 'Le formulaire n’est pas encore disponible.');
    }
}

$raw = file_get_contents('php://input');
if (!is_string($raw) || strlen($raw) > 16000) reply(400, 'Requête invalide.');
$payload = json_decode($raw, true);
if (!is_array($payload)) reply(400, 'Requête invalide.');

$nom = field($payload, 'nom', 100);
$entreprise = field($payload, 'entreprise', 120);
$email = field($payload, 'email', 200);
$besoin = field($payload, 'besoin', 100);
$message = field($payload, 'message', 4000);
$token = field($payload, 'turnstileToken', 2048);

$allowedNeeds = [
    'Conception de logiciel sur mesure',
    'Prestations informatiques',
    'Conseil en gestion',
    'Vente de logiciels',
    'Autre demande',
];
if ($nom === '' || $message === '' || !filter_var($email, FILTER_VALIDATE_EMAIL)
    || !in_array($besoin, $allowedNeeds, true) || $token === '') {
    reply(400, 'Veuillez vérifier les champs et la protection anti-robots.');
}

// La vérification est faite côté serveur : le jeton client n'est pas une preuve suffisante.
$verifyRequest = curl_init('https://challenges.cloudflare.com/turnstile/v0/siteverify');
if ($verifyRequest === false) reply(502, 'Service de vérification indisponible.');
curl_setopt_array($verifyRequest, [
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => http_build_query([
        'secret' => getenv('TURNSTILE_SECRET_KEY'),
        'response' => $token,
    ]),
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_CONNECTTIMEOUT => 5,
    CURLOPT_TIMEOUT => 15,
]);
$verifyBody = curl_exec($verifyRequest);
$verifyCode = (int) curl_getinfo($verifyRequest, CURLINFO_HTTP_CODE);
curl_close($verifyRequest);
if (!is_string($verifyBody) || $verifyCode !== 200) {
    reply(502, 'Service de vérification indisponible.');
}
$verification = json_decode($verifyBody, true);
$hostname = $verification['hostname'] ?? '';
$allowedHosts = ['jalauris-solutions.fr', 'www.jalauris-solutions.fr'];
if (!is_array($verification) || ($verification['success'] ?? false) !== true
    || !is_string($hostname) || !in_array($hostname, $allowedHosts, true)) {
    reply(400, 'Vérification anti-robots refusée. Veuillez réessayer.');
}

$lines = [
    'Nouvelle demande depuis JALAURIS Solutions',
    '',
    'Nom : ' . $nom,
    'Entreprise : ' . $entreprise,
    'Email : ' . $email,
    'Besoin : ' . $besoin,
    '',
    'Message :',
    $message,
];
$text = implode("\n", $lines);
$send = postJson('https://api.resend.com/emails', [
    'from' => getenv('CONTACT_FROM_EMAIL'),
    'to' => [getenv('CONTACT_TO_EMAIL')],
    'reply_to' => $email,
    'subject' => '[JALAURIS] ' . $besoin,
    'text' => $text,
    'html' => '<pre style="white-space:pre-wrap;font-family:sans-serif">'
        . htmlspecialchars($text, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8')
        . '</pre>',
], ['Authorization: Bearer ' . getenv('RESEND_API_KEY')]);

if ($send === null || $send['status'] < 200 || $send['status'] >= 300) {
    error_log('Envoi Resend refusé par le prestataire.');
    reply(502, 'Impossible d’envoyer le message actuellement.');
}
reply(200, 'Votre demande a bien été envoyée.');

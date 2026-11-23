<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

function respond(int $status, array $payload): never {
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    header('Allow: GET');
    respond(405, ['error' => 'Méthode non autorisée']);
}

// Les secrets ne doivent jamais être enregistrés dans ce fichier.
// Leur emplacement privé sur Gandi sera configuré lors de la mise en service.
$required = ['TURNSTILE_SITE_KEY', 'TURNSTILE_SECRET_KEY', 'RESEND_API_KEY', 'CONTACT_FROM_EMAIL', 'CONTACT_TO_EMAIL'];
$configured = true;
foreach ($required as $name) {
    if (trim((string) getenv($name)) === '') {
        $configured = false;
        break;
    }
}

respond(200, [
    'configured' => $configured,
    'siteKey' => $configured ? getenv('TURNSTILE_SITE_KEY') : null,
]);

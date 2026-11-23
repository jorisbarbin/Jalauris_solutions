<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

function respond(int $status, array $payload): never {
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'GET') {
    header('Allow: GET');
    respond(405, ['error' => 'Méthode non autorisée']);
}

// Configuration privée hors de htdocs : ne jamais publier de clés secrètes dans GitHub.
$configPath = '/srv/data/web/vhosts/jalauris-solutions.fr/config/jalauris-config.php';
$config = is_readable($configPath) ? require $configPath : null;
$required = ['TURNSTILE_SITE_KEY', 'TURNSTILE_SECRET_KEY', 'RESEND_API_KEY', 'CONTACT_FROM_EMAIL', 'CONTACT_TO_EMAIL'];
$configured = is_array($config);
if ($configured) {
    foreach ($required as $name) {
        if (!isset($config[$name]) || !is_string($config[$name]) || trim($config[$name]) === '') {
            $configured = false;
            break;
        }
    }
}

respond(200, [
    'configured' => $configured,
    'siteKey' => $configured ? $config['TURNSTILE_SITE_KEY'] : null,
]);

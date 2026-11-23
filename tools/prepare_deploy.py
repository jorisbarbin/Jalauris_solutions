"""Build an explicit public allowlist; never copy private config or internal docs."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = [
    'index.html', 'logiciels-sur-mesure.html', 'prestations-informatiques.html',
    'conseil-en-gestion.html', 'vente-de-logiciels.html', 'mentions-legales.html',
    'politique-confidentialite.html', 'styles.css', 'script.js', 'favicon.ico',
    'favicon.svg', 'robots.txt', 'sitemap.xml',
]
PHP = {'gandi/api/contact.php': 'api/contact.php',
       'gandi/api/contact-config.php': 'api/contact-config.php'}

def prepare(target):
    target = Path(target)
    target.mkdir(exist_ok=False)
    for source, destination in [(p, p) for p in PUBLIC] + list(PHP.items()) + [('gandi/.htaccess', '.htaccess')]:
        src = ROOT / source
        if src.is_symlink() or not src.is_file():
            raise ValueError(f'Invalid public source: {source}')
        dst = target / destination
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    print(f'{len(PUBLIC) + len(PHP) + 1} public files prepared; private config excluded.')

if __name__ == '__main__':
    prepare(ROOT / '_gandi_deploy')

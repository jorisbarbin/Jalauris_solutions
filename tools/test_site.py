import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_deploy import ROOT, PUBLIC, prepare

class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.tags=[]; self.feed(text)
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

class SiteTests(unittest.TestCase):
    def test_metadata_links_and_accessibility_structure(self):
        for name in PUBLIC:
            if not name.endswith('.html'): continue
            page=Page((ROOT/name).read_text())
            self.assertEqual(sum(tag=='h1' for tag,_ in page.tags),1,name)
            self.assertIn(('html', {'lang':'fr'}),page.tags)
            canonical=[a['href'] for t,a in page.tags if t=='link' and a.get('rel')=='canonical']
            self.assertEqual(canonical,['https://jalauris-solutions.fr/'+('' if name=='index.html' else name)])
            og={a['property']:a['content'] for t,a in page.tags if t=='meta' and a.get('property','').startswith('og:')}
            self.assertEqual(og['og:url'],canonical[0]); self.assertTrue(og['og:title']); self.assertTrue(og['og:description'])
            for tag,attrs in page.tags:
                link=attrs.get('href') or attrs.get('src')
                if not link: continue
                u=urlsplit(link)
                if u.scheme or u.netloc: continue
                target=ROOT/(u.path.lstrip('/') or name)
                if u.path=='/': target=ROOT/'index.html'
                self.assertTrue(target.is_file(),f'{name}: {link}')
                if u.fragment and target.suffix=='.html':
                    self.assertIn(u.fragment,{a.get('id') for _,a in Page(target.read_text()).tags},f'{name}: {link}')
    def test_sitemap(self):
        tree=ET.parse(ROOT/'sitemap.xml')
        urls=[x.text for x in tree.findall('.//{*}loc')]
        self.assertEqual(len(urls),7); self.assertEqual(len(set(urls)),7)
        self.assertIn('Sitemap: https://jalauris-solutions.fr/sitemap.xml',(ROOT/'robots.txt').read_text())
    def test_deployment_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'public'; prepare(output)
            files={p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
            self.assertEqual(files,set(PUBLIC)|{'api/contact.php','api/contact-config.php','.htaccess'})
            self.assertFalse(any('jalauris-config' in p or p.startswith(('config/','docs/','tests/')) for p in files))

if __name__=='__main__': unittest.main()

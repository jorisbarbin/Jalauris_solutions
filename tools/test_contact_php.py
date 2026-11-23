"""Exercise real PHP rejection paths with dummy config in an isolated copy, no network calls."""
import json
import subprocess
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PRIVATE='/srv/data/web/vhosts/jalauris-solutions.fr/config/jalauris-config.php'
with tempfile.TemporaryDirectory() as tmp:
    d=Path(tmp)
    config=d/'fixture.php'
    config.write_text("<?php return array_fill_keys(['TURNSTILE_SITE_KEY','TURNSTILE_SECRET_KEY','RESEND_API_KEY','CONTACT_FROM_EMAIL','CONTACT_TO_EMAIL'], 'dummy');")
    for name in ['contact.php','contact-config.php']:
        text=(ROOT/'gandi/api'/name).read_text()
        assert text.count(PRIVATE)==1
        # CLI has no php://input stream; stdin supplies the test payload instead.
        (d/name).write_text(text.replace(PRIVATE,str(config)).replace('php://input','php://stdin'))
    cases=[('contact.php','GET',{},'',405),
           ('contact.php','POST',{'CONTENT_TYPE':'text/plain'},'{}',415),
           ('contact.php','POST',{'CONTENT_TYPE':'application/json','HTTP_ORIGIN':'https://example.org'},'{}',403),
           ('contact.php','POST',{'CONTENT_TYPE':'application/json','CONTENT_LENGTH':'16001'},'',413),
           ('contact.php','POST',{'CONTENT_TYPE':'application/json'},'{}',400),
           ('contact.php','POST',{'CONTENT_TYPE':'application/json'},'{',400),
           ('contact.php','POST',{'CONTENT_TYPE':'application/json'},'x'*16001,400),
           ('contact-config.php','POST',{},'',405)]
    for name,method,env,body,wanted in cases:
        env['REQUEST_METHOD']=method
        setup=''.join('$_SERVER['+json.dumps(k)+']='+json.dumps(v)+';' for k,v in env.items())
        code=setup+'register_shutdown_function(function(){fwrite(STDERR,(string)http_response_code());}); require '+json.dumps(str(d/name))+';'
        run=subprocess.run(['php','-r',code],input=body,text=True,capture_output=True,check=True)
        assert run.stderr==str(wanted),(name,method,run.stderr)
        assert isinstance(json.loads(run.stdout),dict)
    print(f'PASS: {len(cases)} PHP rejection cases; no email or external validation sent.')

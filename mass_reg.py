import sys, os, time, random, string, re, json
import requests
from seleniumbase import SB

# ============================================================
# CONFIG (env vars with fallbacks)
# ============================================================
MAIL_API_BASE = "https://mailapi.niggahunter.qzz.io/inbox"
MAIL_DOMAIN = "niggahunter.qzz.io"
REGISTER_URL = "https://app.zenserp.com/register?plan=free"
HOME_URL = "https://app.zenserp.com/"

TG_TOKEN = os.environ.get("TG_TOKEN", "8885396474:AAEqYW2cvEw9vl7zafpljGQaXQM0ihLASOo")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "-1004473345034")

WORD_POOL = [
    "ash","fox","wolf","hawk","bear","lion","tiger","eagle","storm","blaze",
    "frost","shadow","thunder","cyber","pixel","ghost","phantom","ninja",
    "dragon","delta","alpha","omega","nova","echo","titan","atlas","zero",
    "onyx","apex","vortex","prism","raven","viper","cobra","atlas","zephyr"
]
FIRST = ["James","John","Robert","Mary","Sarah","David","Mike","Chris","Anna","Emma"]
LAST = ["Smith","Johnson","Brown","Davis","Wilson","Taylor","Clark","Hall","King","Wright"]
CITIES = ["Dallas","Houston","Austin","Denver","Boston","Miami","Seattle","Phoenix","Tampa","Atlanta"]
STATES = ["Texas","California","Florida","New York","Colorado","Washington","Arizona","Georgia","Ohio","Nevada"]

# ============================================================
# CLI ARGS: python mass_reg.py <shard_num> <total_shards> <total_accounts>
# ============================================================
SHARD = int(sys.argv[1]) if len(sys.argv) > 1 else 1
TOTAL_SHARDS = int(sys.argv[2]) if len(sys.argv) > 2 else 15
TOTAL_ACCOUNTS = int(sys.argv[3]) if len(sys.argv) > 3 else 100

# Split accounts across shards: 100 accs / 15 shards -> 10 shards get 7, 5 get 6
base = TOTAL_ACCOUNTS // TOTAL_SHARDS
extra = TOTAL_ACCOUNTS % TOTAL_SHARDS
MY_COUNT = base + (1 if SHARD <= extra else 0)

os.makedirs("results", exist_ok=True)
ACCOUNTS_FILE = f"results/accounts_shard_{SHARD:02d}.txt"
KEYS_FILE = f"results/keys_shard_{SHARD:02d}.txt"
TAG = f"S{SHARD}"

# ============================================================
# DATA GEN (local, instant)
# ============================================================
def gen_all():
    return {
        "email": f"{''.join(random.sample(WORD_POOL,3))}{random.randint(100,999)}@{MAIL_DOMAIN}",
        "password": f"{''.join(random.choices(string.ascii_letters+string.digits,k=10))}!Aa1",
        "name": f"{random.choice(FIRST)} {random.choice(LAST)}",
        "address": str(random.randint(1000, 9999)),
        "addr2": f"Apt {random.randint(1,20)}{random.choice(['A','B','C'])}",
        "city": random.choice(CITIES),
        "state": random.choice(STATES),
        "zip": str(random.randint(10000, 99999)),
    }

# ============================================================
# MAIL
# ============================================================
def check_inbox(email, timeout=90):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{MAIL_API_BASE}/{email}", timeout=8)
            if r.status_code == 200:
                d = r.json()
                if d.get("success") and d.get("count", 0) > 0:
                    return d["emails"]
        except:
            pass
        time.sleep(2)
    return None

def extract_verify_link(emails):
    pattern = r'https://app\.zenserp\.com/email/verify/\d+/[a-f0-9]+\?expires=\d+&signature=[a-f0-9]+'
    for em in emails:
        if "verify" not in em.get("subject", "").lower():
            continue
        for body in [em.get("text_body",""), em.get("html_body","")]:
            m = re.search(pattern, body)
            if m:
                return m.group(0)
    return None

# ============================================================
# SAVE
# ============================================================
def save(email, password, api_key):
    valid = api_key and api_key not in ("NOT_FOUND","ERROR","NO_EMAIL","NO_LINK","REG_FAILED","NO_BUTTON")
    with open(ACCOUNTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{email}:{password}\n")
    if valid:
        with open(KEYS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{api_key}\n")
    return valid

# ============================================================
# ONE ACCOUNT — reliable method: sb.type (Vue-safe) + solve_captcha
# ============================================================
def do_one():
    d = gen_all()
    email, password = d["email"], d["password"]

    try:
        with SB(uc=True, test=True, locale="en", headed=True) as sb:
            sb.activate_cdp_mode()
            sb.goto(REGISTER_URL)
            sb.wait_for_element("#name", timeout=20)
            sb.sleep(1)

            # Fill — sb.type pastes instantly and Vue sees it (proven working)
            sb.type("#name", d["name"])
            sb.type("#email", email)
            sb.type("#password", password)
            sb.type("#password_confirmation", password)
            sb.type('input[id^="address_"]', d["address"])
            try:
                sb.type('input[id^="address_line_2_"]', d["addr2"])
            except:
                pass
            sb.type('input[id^="city_"]', d["city"])
            sb.type('input[id^="State_"]', d["state"])
            sb.type('input[placeholder="Postal Code"]', d["zip"])
            sb.select_option_by_text('select[id^="country_"]', "United States")
            sb.sleep(0.5)

            # Captcha + click with fallbacks
            sb.solve_captcha()
            try:
                sb.click('form button.btn-primary')
            except:
                sb.execute_script(
                    "var b=document.querySelector('button.btn-primary');if(b)b.click();"
                )
            sb.sleep(5)

            # Confirm registration
            page = sb.get_page_source().lower()
            url_now = sb.get_current_url().lower()
            registered = any(x in page for x in ["verify your email","check your email","dashboard"]) \
                         or "register" not in url_now

            if not registered:
                # retry once — captcha token may have expired
                print(f"[{TAG}] retry registration...")
                sb.solve_captcha()
                try:
                    sb.click('form button.btn-primary')
                except:
                    sb.execute_script("var b=document.querySelector('button.btn-primary');if(b)b.click();")
                sb.sleep(5)
                page = sb.get_page_source().lower()
                registered = any(x in page for x in ["verify your email","check your email","dashboard"]) \
                             or "register" not in url_now

            if not registered:
                print(f"[{TAG}] ❌ reg failed {email}")
                save(email, password, "REG_FAILED")
                return False

            print(f"[{TAG}] ✅ registered {email[:30]}")

            # Mail
            time.sleep(8)
            emails = check_inbox(email, timeout=90)
            if not emails:
                print(f"[{TAG}] ❌ no email")
                save(email, password, "NO_EMAIL")
                return False
            link = extract_verify_link(emails)
            if not link:
                print(f"[{TAG}] ❌ no link")
                save(email, password, "NO_LINK")
                return False

            # Verify — same session, no login needed
            sb.goto(link)
            sb.sleep(3)

            # Homepage → key
            sb.goto(HOME_URL)
            sb.wait_for_element("#key", timeout=12)
            api_key = sb.execute_script("var e=document.querySelector('#key');return e?e.value:null;")

            if api_key and len(api_key) > 10:
                print(f"[{TAG}] 🔑 {api_key}")
                save(email, password, api_key)
                return True
            else:
                print(f"[{TAG}] ⚠️ no key")
                save(email, password, "NOT_FOUND")
                return False

    except Exception as e:
        print(f"[{TAG}] ❌ {str(e)[:80]}")
        try:
            save(email, password, "ERROR")
        except:
            pass
        return False

# ============================================================
# MAIN — sequential per machine, staggered start per shard
# ============================================================
def main():
    # Stagger so 15 machines don't hit register at the same second
    stagger = SHARD * random.uniform(2, 4)
    time.sleep(stagger)

    print(f"=== SHARD {SHARD}/{TOTAL_SHARDS} | {MY_COUNT} accounts ===")
    ok = 0
    t0 = time.time()
    for i in range(MY_COUNT):
        print(f"\n[{TAG}] --- Account {i+1}/{MY_COUNT} ---")
        if do_one():
            ok += 1
        time.sleep(random.uniform(2, 5))  # human-ish gap between accounts

    print(f"\n=== SHARD {SHARD} DONE: {ok}/{MY_COUNT} keys | {time.time()-t0:.0f}s ===")

    # Write summary file for merge job
    with open(f"results/summary_shard_{SHARD:02d}.txt", "w") as f:
        f.write(f"shard={SHARD} ok={ok} total={MY_COUNT}\n")

if __name__ == "__main__":
    main()

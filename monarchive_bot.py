import imaplib
import email
import sqlite3
import time
import logging
import requests
import schedule
from datetime import datetime
from email.header import decode_header

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(**name**)

COMPTES = [
{
“nom”: “Gmail”,
“email”: “karadiabyy224@gmail.com”,
“password”: “bcsh xpld qbyx oxqy”,
“imap”: “imap.gmail.com”,
“port”: 993
},
{
“nom”: “iCloud”,
“email”: “karadiaby@icloud.com”,
“password”: “cbpt-dvax-gthq-bwgd”,
“imap”: “imap.mail.me.com”,
“port”: 993
}
]

TELEGRAM_TOKEN = “8720932052:AAEqm7Pn6JRtHIIyZukSw19YoEo0anZ9gSM”
TELEGRAM_CHAT_ID = “8779757061”
DB_NAME = “monarchive.db”

CATEGORIES = {
“facture”: [
“facture”, “invoice”, “recu”, “receipt”, “paiement”, “payment”,
“montant”, “amount”, “total”, “ttc”, “ht”, “eur”,
“edf”, “engie”, “sfr”, “orange”, “free”, “bouygues”, “sosh”,
“eau”, “gaz”, “electricite”, “abonnement”,
“prelevement”, “echeance”
],
“creance”: [
“relance”, “impayes”, “dette”, “recouvrement”,
“mise en demeure”, “huissier”, “litige”, “contentieux”,
“retard de paiement”, “solde du”, “creance”,
“reminder”, “overdue”, “unpaid”
],
“contrat”: [
“contrat”, “contract”, “accord”, “agreement”, “convention”,
“signature”, “signer”, “avenant”, “conditions generales”,
“cgv”, “cgu”, “bail”, “location”, “assurance”, “garantie”,
“souscription”, “engagement”, “mandat”
],
“courrier”: [
“courrier”, “lettre”, “recommande”, “avis”,
“notification”, “convocation”, “assignation”, “jugement”,
“tribunal”, “administration”, “prefecture”, “impots”,
“urssaf”, “caf”, “cpam”, “securite sociale”,
“amende”, “rappel”, “urgent”, “important”
]
}

SPAM_MOTS = [
“newsletter”, “promo”, “promotion”, “offre”, “soldes”, “reduction”,
“gratuit”, “unsubscribe”, “desinscription”,
“marketing”, “publicite”, “deal”, “discount”, “sale”,
“noreply”, “no-reply”, “donotreply”
]

def init_db():
conn = sqlite3.connect(DB_NAME)
c = conn.cursor()
c.execute(’’‘CREATE TABLE IF NOT EXISTS documents (
id INTEGER PRIMARY KEY AUTOINCREMENT,
email_id TEXT UNIQUE,
compte TEXT,
categorie TEXT,
titre TEXT,
montant TEXT,
emetteur TEXT,
statut TEXT,
date_ajout TEXT
)’’’)
conn.commit()
conn.close()

def already_processed(email_id):
conn = sqlite3.connect(DB_NAME)
c = conn.cursor()
c.execute(“SELECT 1 FROM documents WHERE email_id = ?”, (email_id,))
res = c.fetchone()
conn.close()
return res is not None

def save_document(email_id, compte, doc):
conn = sqlite3.connect(DB_NAME)
c = conn.cursor()
c.execute(’’‘INSERT OR IGNORE INTO documents
(email_id, compte, categorie, titre, montant, emetteur, statut, date_ajout)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)’’’, (
email_id, compte,
doc.get(“categorie”, “autre”),
doc.get(“titre”, “”),
doc.get(“montant”, “”),
doc.get(“emetteur”, “”),
doc.get(“statut”, “en-attente”),
datetime.now().isoformat()
))
conn.commit()
conn.close()

def decode_str(s):
if not s:
return “”
parts = decode_header(s)
result = “”
for part, enc in parts:
if isinstance(part, bytes):
result += part.decode(enc or “utf-8”, errors=“ignore”)
else:
result += part
return result

def get_email_body(msg):
body = “”
if msg.is_multipart():
for part in msg.walk():
ct = part.get_content_type()
cd = str(part.get(“Content-Disposition”, “”))
if ct == “text/plain” and “attachment” not in cd:
try:
body = part.get_payload(decode=True).decode(“utf-8”, errors=“ignore”)
break
except:
pass
else:
try:
body = msg.get_payload(decode=True).decode(“utf-8”, errors=“ignore”)
except:
pass
return body[:2000]

def lire_emails(compte):
mails = []
try:
mail = imaplib.IMAP4_SSL(compte[“imap”], compte[“port”])
mail.login(compte[“email”], compte[“password”])
mail.select(“INBOX”)
_, data = mail.search(None, “UNSEEN”)
ids = data[0].split()
if not ids:
_, data = mail.search(None, “ALL”)
ids = data[0].split()[-20:]
logger.info(f”{compte[‘nom’]} : {len(ids)} email(s)”)
for eid in ids[-20:]:
try:
*, msg_data = mail.fetch(eid, “(RFC822)”)
msg = email.message_from_bytes(msg_data[0][1])
sujet = decode_str(msg.get(“Subject”, “”))
expediteur = decode_str(msg.get(“From”, “”))
body = get_email_body(msg)
email_id = f”{compte[‘nom’]}*{eid.decode()}”
mails.append({
“id”: email_id,
“sujet”: sujet,
“expediteur”: expediteur,
“body”: body
})
except Exception as e:
logger.error(f”Erreur email {eid}: {e}”)
continue
mail.logout()
except Exception as e:
logger.error(f”Erreur IMAP {compte[‘nom’]}: {e}”)
return mails

def extraire_montant(texte):
import re
patterns = [
r’(\d+[,.]\d{2})\s*€’,
r’€\s*(\d+[,.]\d{2})’,
r’montant\s*:?\s*(\d+[,.]\d{2})’,
r’total\s*:?\s*(\d+[,.]\d{2})’,
]
for pattern in patterns:
match = re.search(pattern, texte, re.IGNORECASE)
if match:
return match.group(1) + “€”
return “”

def extraire_emetteur(expediteur):
if “<” in expediteur:
nom = expediteur.split(”<”)[0].strip().strip(’”’)
if nom:
return nom
if “@” in expediteur:
domaine = expediteur.split(”@”)[1].split(”>”)[0]
return domaine.split(”.”)[0].title()
return expediteur[:50]

def analyser_email(mail_data):
texte = f”{mail_data[‘sujet’]} {mail_data[‘body’]}”.lower()
expediteur = mail_data[‘expediteur’].lower()

```
for mot in SPAM_MOTS:
    if mot in texte or mot in expediteur:
        return None

scores = {}
for categorie, mots in CATEGORIES.items():
    score = sum(1 for mot in mots if mot in texte)
    if score > 0:
        scores[categorie] = score

if not scores:
    return None

categorie = max(scores, key=scores.get)
montant = extraire_montant(texte)
emetteur = extraire_emetteur(mail_data['expediteur'])

statut = "en-attente"
if any(m in texte for m in ["paye", "regle", "confirme"]):
    statut = "paye"
elif any(m in texte for m in ["impayes", "relance", "retard"]):
    statut = "impayes"
elif any(m in texte for m in ["signe", "valide"]):
    statut = "signe"

return {
    "categorie": categorie,
    "titre": mail_data['sujet'][:80],
    "montant": montant,
    "emetteur": emetteur,
    "statut": statut
}
```

def notifier_telegram(doc, compte):
cat_emoji = {
“facture”: “🧾”,
“creance”: “💸”,
“contrat”: “📋”,
“courrier”: “✉️”,
“autre”: “📁”
}
emoji = cat_emoji.get(doc.get(“categorie”, “autre”), “📁”)
texte = (
f”{emoji} NOUVEAU DOCUMENT DETECTE\n\n”
f”📌 {doc.get(‘titre’, ‘’)}\n”
f”📂 {doc.get(‘categorie’, ‘’).upper()}\n”
f”👤 {doc.get(‘emetteur’, ‘’)}\n”
)
if doc.get(“montant”):
texte += f”💶 {doc.get(‘montant’)}\n”
texte += f”📊 Statut : {doc.get(‘statut’)}\n”
texte += f”📧 Compte : {compte}”

```
try:
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": texte},
        timeout=10
    )
    logger.info(f"Telegram envoye : {doc.get('titre', '')[:40]}")
except Exception as e:
    logger.error(f"Erreur Telegram: {e}")
```

def job():
logger.info(“Scan des boites mail…”)
init_db()
total = 0
for compte in COMPTES:
logger.info(f”Lecture {compte[‘nom’]}…”)
mails = lire_emails(compte)
for mail_data in mails:
if already_processed(mail_data[“id”]):
continue
logger.info(f”Analyse : {mail_data[‘sujet’][:50]}”)
doc = analyser_email(mail_data)
if doc:
save_document(mail_data[“id”], compte[“nom”], doc)
notifier_telegram(doc, compte[“nom”])
total += 1
else:
save_document(mail_data[“id”], compte[“nom”], {
“categorie”: “autre”,
“titre”: mail_data[“sujet”][:50]
})
time.sleep(0.5)
logger.info(f”Scan termine — {total} documents detectes”)

if **name** == “**main**”:
logger.info(“MonArchive Bot demarre…”)
job()
schedule.every(1).hours.do(job)
while True:
schedule.run_pending()
time.sleep(60)

# ⛏️ Minecraft Italia - Bot Monitoraggio Voti & Discord Webhook

Uno script standalone in Python, leggero e sicuro, progettato per analizzare quotidianamente i voti ricevuti dal tuo server Minecraft su **Minecraft Italia** (minecraft-italia.net). Lo script tiene traccia dei dati storici localmente e invia automaticamente report giornalieri e mensili (completi di statistiche avanzate e grafici generati con `matplotlib`) al tuo canale Discord tramite **Webhook**.

Il progetto è strutturato in modo da non esporre le credenziali sensibili, leggendole da un file `.env` locale che può essere escluso dal tracciamento Git.

---

## 🚀 Caratteristiche Principali
* **Nessuna dipendenza pesante**: Utilizza richieste HTTP standard tramite la libreria `requests`, evitando la necessità di far girare un intero bot Discord in background (es. tramite `discord.py`).
* **Integrazione API Minecraft Italia**: Interroga l'endpoint ufficiale `/vote/server` passando in modo sicuro il token di autenticazione e l'ID del server.
* **Database JSON Locale**: Memorizza giorno per giorno lo storico dei voti in `votes_history.json` con scrittura atomica sicura per prevenire corruzioni di dati in caso di crash.
* **Report Giornalieri Eleganti**: Invia un messaggio Embed a Discord formattato con emoji personalizzate che mostra in modo chiaro chi ha votato e chi ha saltato il voto tra i giocatori monitorati.
* **Report Mensili con Grafici Premium**: L'ultimo giorno del mese lo script analizza lo storico, calcola i "Campioni del Mese" (100% di voti) e la classifica "All-Time", generando due grafici a barre eleganti ad alta definizione via `matplotlib` inviati direttamente come allegati a Discord.
* **Gestione degli Errori e Logging**: Qualsiasi errore di rete o HTTP viene intercettato, scritto nel file `vote_monitor.log` per futura consultazione e notificato su Discord per allertare gli amministratori.

---

## 📂 Struttura del Progetto
```text
Minecraft_Italia_Bot/
│
├── .env                       # File contenente le chiavi segrete (DA NON CARICARE SU GITHUB)
├── .env.example               # Modello di esempio per le variabili d'ambiente
├── players.json               # Lista dei giocatori (Minecraft Username) da monitorare
├── votes_history.json         # Database locale dello storico dei voti giornalieri
├── vote_monitor.log           # File di log autogenerato con eventi ed errori
├── requirements.txt           # Dipendenze Python del progetto
├── minecraft_vote_monitor.py  # Script Python principale contenente la logica
└── README.md                  # Questa guida all'uso
```

---

## 🛠️ Requisiti e Installazione

### 1. Prerequisiti
Assicurati di avere installato sul tuo sistema:
* **Python 3.8 o superiore**
* **Pip** (il gestore di pacchetti Python)

### 2. Clonare e Configurare il Progetto
1. Copia i file del progetto sul tuo server o computer locale.
2. Naviga nella cartella del progetto ed installa le dipendenze necessarie:
   ```bash
   pip install -r requirements.txt
   ```

### 3. Configurazione delle Variabili d'Ambiente (`.env`)
Rinomina il file `.env.example` in `.env` e compila le variabili richieste:
```ini
# Token API del server su Minecraft Italia
MINECRAFT_ITALIA_API_TOKEN=il_tuo_token_api_privato

# ID del server (puoi trovarlo nell'URL della pagina del tuo server)
SERVER_ID=12345

# URL completo del Webhook Discord del canale dove ricevere i report
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxx/xxxx
```

### 4. Aggiungere i Giocatori da Monitorare (`players.json`)
Il file `players.json` contiene una lista in formato JSON con i Minecraft Username dei membri o dello staff da monitorare. Modificalo inserendo i nomi reali:
```json
[
  "Steve",
  "Alex",
  "Grumm",
  "Notch"
]
```
*(Nota: Lo script normalizza i nomi per i confronti ignorando maiuscole/minuscole, ma mantiene la formattazione originale dei nomi per l'invio dei report).*

---

## 🧪 Eseguire Test Manuali da Terminale

Puoi testare il funzionamento dello script, l'invio al Webhook Discord e la generazione dei grafici direttamente dal terminale tramite specifici parametri a riga di comando:

* **Test Completo (Giornaliero + Mensile con Grafici)**:
  ```bash
  ./venv/bin/python3 minecraft_vote_monitor.py --test
  ```
* **Test Solo Report Giornaliero Reale** (scarica i voti reali odierni del server dal sito Minecraft Italia ed invia il report Embed a Discord, senza salvare nulla nel database storico locale per evitare di inquinarlo):
  ```bash
  ./venv/bin/python3 minecraft_vote_monitor.py --test-daily
  ```
* **Test Solo Report Mensile con Grafici** (legge lo storico dei dati reali salvati in `votes_history.json`, elabora le metriche, genera i due grafici Matplotlib premium ed invia il messaggio con allegati a Discord):
  ```bash
  ./venv/bin/python3 minecraft_vote_monitor.py --test-monthly
  ```

---

## ⏱️ Automazione in 3 Fasi (Cron Job)

Per garantire la massima puntualità ed evitare i ritardi fisiologici delle esecuzioni pianificate native di GitHub Actions, lo script supporta una suddivisione del monitoraggio in **3 fasi giornaliere**.

Puoi implementare questa automazione in due modi: tramite un **Servizio Cron Online** (consigliato, per un'esecuzione 100% cloud-free) o tramite il **Crontab locale** di Linux.

---

### 🌐 Opzione A: Serverless Cloud tramite Servizio Cron Online (Consigliato)

Puoi utilizzare un servizio gratuito di Web-Cron online (come [Cron-job.org](https://cron-job.org/)) per forzare l'avvio delle 3 fasi del workflow di GitHub Actions tramite le API di GitHub.

#### 1. Genera un GitHub Personal Access Token (PAT)
Per consentire al servizio esterno di avviare il workflow, devi generare un token di accesso:
1. Su GitHub, vai su **Settings** (del tuo account) > **Developer Settings** > **Personal Access Tokens** > **Tokens (classic)**.
2. Clicca su **Generate new token (classic)**.
3. Seleziona lo scope **`workflow`** (o `repo` se il repository è privato) e genera il token.
4. Copia il token generato (lo userai nei passaggi successivi).

#### 2. Configura le 3 Invocazioni sul Servizio Cron
Crea tre cron job differenti sul pannello del tuo servizio Cron Web con le seguenti impostazioni comuni:
* **Metodo HTTP**: `POST`
* **URL**: `https://api.github.com/repos/<IL_TUO_USER_GITHUB>/<IL_TUO_REPOSITOR_BOT>/actions/workflows/vote_monitor.yml/dispatches`
* **Header Richiesti**:
  * `Authorization`: `Bearer <IL_TUO_GITHUB_PAT>`
  * `Accept`: `application/vnd.github.v3+json`
  * `User-Agent`: `CronJob-Service` (qualsiasi stringa identificativa, richiesta da GitHub)

Quindi definisci i diversi corpi della richiesta (`Body / Payload`) e gli orari:

1. **Ore 20:00 (Sollecito Pomeridiano)**:
   * **Orario**: Ogni giorno alle `20:00` (ore `18:00` UTC)
   * **Body (JSON)**:
     ```json
     {"ref": "main", "inputs": {"phase": "--reminder"}}
     ```
2. **Ore 23:55 (Raccolta Silenziosa)**:
   * **Orario**: Ogni giorno alle `23:55` (ore `21:55` UTC)
   * **Body (JSON)**:
     ```json
     {"ref": "main", "inputs": {"phase": "--collect"}}
     ```
3. **Ore 09:00 (Riepilogo Giornaliero e Mensile)**:
   * **Orario**: Ogni giorno alle `09:00` (ore `07:00` UTC)
   * **Body (JSON)**:
     ```json
     {"ref": "main", "inputs": {"phase": "--send-summary"}}
     ```

---

### 🖥️ Opzione B: Esecuzione Locale tramite Crontab (Linux)

Se preferisci ospitare ed eseguire lo script in locale sul tuo server o VPS, apri il crontab del tuo sistema (`crontab -e`) e inserisci le seguenti tre righe (sostituendo `/percorso/assoluto/` con la cartella reale del tuo progetto):

```text
# 1. Ore 20:00 - Sollecito voti pomeridiano (senza tag)
00 20 * * * cd /percorso/assoluto/Minecraft_Italia_Bot && /percorso/assoluto/Minecraft_Italia_Bot/venv/bin/python3 minecraft_vote_monitor.py --reminder > /dev/null 2>&1

# 2. Ore 23:55 - Raccolta silenziosa dei voti odierni
55 23 * * * cd /percorso/assoluto/Minecraft_Italia_Bot && /percorso/assoluto/Minecraft_Italia_Bot/venv/bin/python3 minecraft_vote_monitor.py --collect > /dev/null 2>&1

# 3. Ore 09:00 (Giorno dopo) - Invio riepilogo definitivo (con tag) e grafici mensili
00 09 * * * cd /percorso/assoluto/Minecraft_Italia_Bot && /percorso/assoluto/Minecraft_Italia_Bot/venv/bin/python3 minecraft_vote_monitor.py --send-summary > /dev/null 2>&1
```

---

---

## 📊 Database Storico (`votes_history.json`)
Il database locale si auto-aggiorna ad ogni esecuzione quotidiana memorizzando la data e la lista dei giocatori che hanno votato in quel giorno specifico:
```json
{
  "2026-05-30": ["Steve", "Alex"],
  "2026-05-31": ["Steve", "Alex", "Notch", "Grumm"],
  "2026-06-01": ["Steve", "Grumm"]
}
```
Questo file è vitale per la generazione dei grafici all-time e mensili, quindi si consiglia di farne periodicamente dei backup. Lo script effettua un backup automatico temporaneo `.bak` prima di ogni sovrascrittura.

---

## 🩺 Gestione Errori e Diagnostica
Se qualcosa non dovesse funzionare (es. API di Minecraft Italia offline o webhook non configurato correttamente), controlla il file `vote_monitor.log` autogenerato:
```text
2026-06-01 23:55:01 [INFO] === AVVIO SCRIP MINECRAFT ITALIA VOTE MONITOR ===
2026-06-01 23:55:01 [INFO] Esecuzione odierna: 2026-06-01
2026-06-01 23:55:02 [INFO] Interrogazione API Minecraft Italia per il Server ID: 12345...
2026-06-01 23:55:03 [ERROR] Errore di rete o HTTP durante la chiamata all'API di Minecraft Italia: 502 Bad Gateway
```
In caso di fallimento di rete all'API, lo storico locale `votes_history.json` **non viene modificato** né corrotto e lo script invia una notifica di avviso al webhook di Discord (se raggiungibile).

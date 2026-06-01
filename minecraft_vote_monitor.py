#!/usr/bin/env python3
# -*- coding: utf-8, -*-

"""
Minecraft Italia Vote Monitor & Discord Webhook Reporter
Autore: Alessio Bellan
Descrizione: Script standalone per analizzare i voti giornalieri di un server Minecraft
             su Minecraft Italia, salvare lo storico locale in JSON, e inviare report
             giornalieri ed eleganti report mensili con grafici Matplotlib su Discord.
"""

import os
import sys
import json
import logging
import datetime
import calendar
import shutil
import argparse
from typing import List, Dict, Set, Tuple

# Caricamento librerie di terze parti con gestione degli errori
try:
    import requests
    from dotenv import load_dotenv
except ImportError:
    print("ERRORE: Assicurati di aver installato le dipendenze in 'requirements.txt'!")
    print("Esegui: pip install -r requirements.txt")
    sys.exit(1)

try:
    import matplotlib
    # Forza matplotlib a non usare un backend GUI visto che girerà headless in cron
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
except ImportError:
    print("ERRORE: Matplotlib non è installato! Sarà necessario per i report mensili.")
    print("Esegui: pip install -r requirements.txt")
    sys.exit(1)

# ==========================================
# CONFIGURAZIONE LOGGING
# ==========================================
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vote_monitor.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("VoteMonitor")

# Carica le variabili dal file .env se presente
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
    logger.info("File .env caricato con successo.")
else:
    logger.warning("File .env non trovato nella cartella corrente. Verranno usate le variabili di sistema.")

# Costanti di Configurazione
SERVER_ID = os.getenv("SERVER_ID")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# Validazione configurazioni essenziali
if not SERVER_ID or not DISCORD_WEBHOOK_URL:
    logger.critical("Configurazioni mancanti! Assicurati di impostare "
                    "SERVER_ID e DISCORD_WEBHOOK_URL in .env o come variabili d'ambiente.")
    sys.exit(1)

# File Locali
PLAYERS_FILE = os.path.join(BASE_DIR, "players.json")
VOTES_HISTORY_FILE = os.path.join(BASE_DIR, "votes_history.json")

# ==========================================
# GESTIONE DATI LOCALI (JSON DATABASE)
# ==========================================

def init_files():
    """Inizializza i file players.json e votes_history.json se mancanti."""
    if not os.path.exists(PLAYERS_FILE):
        default_players = ["Steve", "Alex", "Notch", "Grumm"]
        try:
            with open(PLAYERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_players, f, indent=2, ensure_ascii=False)
            logger.info(f"File {PLAYERS_FILE} creato con una lista di giocatori di esempio.")
        except Exception as e:
            logger.error(f"Errore nella creazione di players.json: {e}")

    if not os.path.exists(VOTES_HISTORY_FILE):
        try:
            with open(VOTES_HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump({}, f, indent=2, ensure_ascii=False)
            logger.info(f"File {VOTES_HISTORY_FILE} creato inizializzato vuoto.")
        except Exception as e:
            logger.error(f"Errore nella creazione di votes_history.json: {e}")

def load_players() -> List[str]:
    """Carica la lista dei giocatori da monitorare da players.json."""
    init_files()
    try:
        with open(PLAYERS_FILE, 'r', encoding='utf-8') as f:
            players = json.load(f)
            if isinstance(players, list):
                # Normalizza i nomi rimuovendo spazi bianchi
                return [p.strip() for p in players if isinstance(p, str)]
            logger.error("Il formato di players.json non è una lista valida.")
            return []
    except Exception as e:
        logger.error(f"Errore durante il caricamento di players.json: {e}")
        return []

def load_votes_history() -> Dict[str, List[str]]:
    """Carica lo storico dei voti da votes_history.json."""
    init_files()
    try:
        with open(VOTES_HISTORY_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
            if isinstance(history, dict):
                return history
            logger.error("Il formato di votes_history.json non è un dizionario valido.")
            return {}
    except Exception as e:
        logger.error(f"Errore durante il caricamento di votes_history.json: {e}")
        return {}

def save_votes_history(history: Dict[str, List[str]]) -> bool:
    """Salva lo storico dei voti in modo sicuro usando file temporanei per evitare corruzioni."""
    tmp_file = VOTES_HISTORY_FILE + ".tmp"
    bak_file = VOTES_HISTORY_FILE + ".bak"
    try:
        # 1. Scrive su un file temporaneo
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        
        # 2. Crea un backup del vecchio file se esiste
        if os.path.exists(VOTES_HISTORY_FILE):
            shutil.copy2(VOTES_HISTORY_FILE, bak_file)
            
        # 3. Sostituisce il vecchio file con il nuovo temporaneo
        os.replace(tmp_file, VOTES_HISTORY_FILE)
        
        # 4. Rimuove il backup temporaneo di successo
        if os.path.exists(bak_file):
            os.remove(bak_file)
        return True
    except Exception as e:
        logger.error(f"Errore durante il salvataggio sicuro di votes_history.json: {e}")
        # In caso di disastro, prova a ripristinare il backup se presente
        if os.path.exists(bak_file):
            try:
                os.replace(bak_file, VOTES_HISTORY_FILE)
                logger.info("Ripristinato il database dei voti dal backup locale (.bak).")
            except Exception as re:
                logger.error(f"Impossibile ripristinare il backup dei voti: {re}")
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
        return False

# ==========================================
# INTEGRAZIONE API E WEBHOOK
# ==========================================

def fetch_today_votes(server_id: str) -> List[Dict]:
    """
    Interroga l'API di Minecraft Italia per ottenere l'elenco dei voti odierni del server.
    ENDPOINT: https://minecraft-italia.net/lista/api/vote/server?serverId={server_id}
    """
    url = "https://minecraft-italia.net/lista/api/vote/server"
    params = {"serverId": server_id}
    
    headers = {
        "Accept": "application/json",
        "User-Agent": "Minecraft-Italia-Vote-Monitor/1.0 (Python standalone bot)"
    }
    
    logger.info(f"Interrogazione API Minecraft Italia per il Server ID: {server_id}...")
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        # Solleva un'eccezione se lo status code indica un errore HTTP
        response.raise_for_status()
        
        votes = response.json()
        if isinstance(votes, list):
            logger.info(f"Ricevuti {len(votes)} voti complessivi dall'API.")
            return votes
        else:
            logger.error("L'API non ha restituito una lista JSON come da specifiche.")
            return []
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Errore di rete o HTTP durante la chiamata all'API di Minecraft Italia: {e}")
        # Notifica l'amministratore via Discord dell'errore delle API, garantendo tracciabilità
        send_error_notification_to_discord(f"Impossibile contattare l'API di Minecraft Italia: `{e}`")
        raise e

def send_discord_webhook(payload: Dict, files: Dict = None) -> bool:
    """Invia un payload (testo, embed e opzionalmente file) al canale Discord tramite Webhook."""
    try:
        if files:
            # Invio Multipart se ci sono file (grafici allegati)
            response = requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files, timeout=20)
        else:
            # Invio JSON standard
            headers = {"Content-Type": "application/json"}
            response = requests.post(DISCORD_WEBHOOK_URL, json=payload, headers=headers, timeout=15)
            
        if response.status_code in [200, 204]:
            return True
        else:
            logger.error(f"Discord Webhook ha risposto con codice {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Errore durante l'invio del Webhook a Discord: {e}")
        return False

def send_error_notification_to_discord(error_message: str):
    """Invia una notifica di errore per allertare gli amministratori del server."""
    payload = {
        "embeds": [
            {
                "title": "⚠️ Errore di Monitoraggio Voti",
                "description": f"Si è verificato un errore nello script Minecraft Italia Monitor:\n\n{error_message}",
                "color": 16711680,  # Rosso brillante
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "footer": {
                    "text": "Made by Alessio Bellan • Notifica di Errore"
                }
            }
        ]
    }
    # Invio silenzioso dell'errore (non logga un loop infinito se la connessione è del tutto offline)
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
    except Exception:
        pass

# ==========================================
# REPORT GIORNALIERO
# ==========================================

def process_daily_votes(votes_data: List[Dict], monitored_players: List[str]) -> Tuple[List[str], List[str]]:
    """
    Confronta i voti odierni restituiti dall'API con la lista dei giocatori monitorati.
    Ritorna la tupla: (lista_giocatori_che_hanno_votato, lista_giocatori_che_hanno_saltato)
    """
    # Raccoglie tutti gli username unici dell'API normalizzandoli in minuscolo per il confronto
    voted_usernames_normalized = {vote.get("username", "").strip().lower() for vote in votes_data if vote.get("username")}
    
    # Crea una mappatura case-insensitive per preservare la formattazione originale dei nomi monitorati
    monitored_map = {p.lower(): p for p in monitored_players}
    
    voted_monitored = []
    skipped_monitored = []
    
    for player_normalized, original_name in monitored_map.items():
        if player_normalized in voted_usernames_normalized:
            voted_monitored.append(original_name)
        else:
            skipped_monitored.append(original_name)
            
    # Ordina i risultati in modo alfabetico per una migliore presentazione visiva
    voted_monitored.sort()
    skipped_monitored.sort()
    
    return voted_monitored, skipped_monitored

def send_daily_report(date_str: str, voted_players: List[str], skipped_players: List[str]) -> bool:
    """Costruisce e invia un report giornaliero elegante tramite Discord Embed."""
    
    # Formattazione per la visualizzazione dell'elenco
    voted_text = "\n".join([f"🔹 **{p}**" for p in voted_players]) if voted_players else "*Nessuno dei giocatori monitorati ha votato oggi.*"
    skipped_text = "\n".join([f"🔸 {p}" for p in skipped_players]) if skipped_players else "*Ottimo! Tutti i giocatori monitorati hanno votato oggi!* 🎉"
    
    # Calcolo percentuale di partecipazione
    total = len(voted_players) + len(skipped_players)
    percent = (len(voted_players) / total * 100) if total > 0 else 0
    
    # Sceglie il colore in base alle performance del giorno
    if percent == 100:
        color = 3066993  # Verde smeraldo
    elif percent >= 50:
        color = 16254464  # Giallo / Arancio
    else:
        color = 15158332  # Rosso ruggine
        
    embed = {
        "title": f"⛏️ Report Voti Giornaliero - {date_str}",
        "description": f"Monitoraggio giornaliero dei voti del server su Minecraft Italia.\nPartecipazione odierna: **{percent:.1f}%** ({len(voted_players)}/{total})",
        "color": color,
        "fields": [
            {
                "name": f"✅ Giocatori che hanno votato ({len(voted_players)})",
                "value": voted_text,
                "inline": False
            },
            {
                "name": f"❌ Giocatori che hanno saltato il voto ({len(skipped_players)})",
                "value": skipped_text,
                "inline": False
            }
        ],
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "footer": {
            "text": "Made by Alessio Bellan • Report Automatico"
        }
    }
    
    payload = {"embeds": [embed]}
    return send_discord_webhook(payload)

# ==========================================
# REPORT MENSILE E GRAFICI (MATPLOTLIB)
# ==========================================

def is_last_day_of_month(date_obj: datetime.date) -> bool:
    """Verifica se il giorno specificato è l'ultimo giorno del suo mese."""
    # Se domani cambia il mese (giorno == 1), allora oggi è l'ultimo giorno del mese
    tomorrow = date_obj + datetime.timedelta(days=1)
    return tomorrow.day == 1

def generate_graphics(
    monthly_data: Dict[str, int], 
    all_time_data: Dict[str, int], 
    month_name: str,
    year: int
) -> Tuple[str, str]:
    """
    Genera due grafici eleganti e ad alta definizione con Matplotlib e li salva localmente.
    Ritorna i percorsi assoluti delle immagini generate.
    """
    # Prepariamo i percorsi locali per le immagini PNG temporanee
    path_month = os.path.join(BASE_DIR, "temp_month_votes.png")
    path_all_time = os.path.join(BASE_DIR, "temp_all_time_votes.png")
    
    # ----------------------------------------------------
    # GRAFICO 1: Mese Corrente
    # ----------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    
    # Ordinamento decrescente dei voti per un aspetto professionale
    sorted_month = sorted(monthly_data.items(), key=lambda x: x[1], reverse=True)
    players_m = [item[0] for item in sorted_month]
    votes_m = [item[1] for item in sorted_month]
    
    # Palette colori premium (gradienti di blu-teal moderni)
    colors_m = ['#1d3557' if i == 0 else '#457b9d' if i < 3 else '#a8dadc' for i in range(len(votes_m))]
    if not colors_m:
        colors_m = ['#457b9d']
        
    bars_m = ax.bar(players_m, votes_m, color=colors_m, edgecolor='#2b2d42', linewidth=0.7, width=0.55)
    
    # Abbellimenti grafici premium
    ax.set_title(f"📈 Giorni di Voto - {month_name} {year}", fontsize=14, fontweight='bold', color='#1d3557', pad=15)
    ax.set_ylabel("Giorni Votati", fontsize=10, fontweight='semibold', color='#2b2d42')
    ax.set_ylim(0, 32)
    ax.grid(axis='y', linestyle='--', alpha=0.5, color='#ccc')
    ax.set_axisbelow(True)
    
    # Rimuove i bordi del box per un design minimalista e moderno
    for spine in ['top', 'right', 'left']:
        ax.spines[spine].set_visible(False)
    ax.spines['bottom'].set_color('#2b2d42')
    
    # Aggiunta di etichette dei dati sopra le barre
    for bar in bars_m:
        yval = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width()/2.0, 
            yval + 0.6, 
            f"{int(yval)}", 
            ha='center', 
            va='bottom', 
            fontsize=9, 
            fontweight='bold', 
            color='#1d3557'
        )
        
    plt.tight_layout()
    plt.savefig(path_month, format='png', bbox_inches='tight', transparent=False)
    plt.close()
    
    # ----------------------------------------------------
    # GRAFICO 2: All-Time
    # ----------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    
    # Ordinamento decrescente
    sorted_all = sorted(all_time_data.items(), key=lambda x: x[1], reverse=True)
    players_a = [item[0] for item in sorted_all]
    votes_a = [item[1] for item in sorted_all]
    
    # Palette colori all-time premium (arancio corallo / dorato)
    colors_a = ['#e07a5f' if i == 0 else '#f4f1de' if i < 3 else '#f2cc8f' for i in range(len(votes_a))]
    if not colors_a:
        colors_a = ['#e07a5f']
        
    bars_a = ax.bar(players_a, votes_a, color=colors_a, edgecolor='#3d405b', linewidth=0.7, width=0.55)
    
    # Abbellimenti grafici premium
    ax.set_title("🏆 Voti Complessivi Storici (All-Time)", fontsize=14, fontweight='bold', color='#3d405b', pad=15)
    ax.set_ylabel("Totale Voti Registrati", fontsize=10, fontweight='semibold', color='#3d405b')
    
    # Gestione dinamica dei limiti asse Y per all-time
    max_val = max(votes_a) if votes_a else 10
    ax.set_ylim(0, max_val * 1.15 if max_val > 0 else 10)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    
    ax.grid(axis='y', linestyle='--', alpha=0.5, color='#ccc')
    ax.set_axisbelow(True)
    
    # Rimuove i bordi del box
    for spine in ['top', 'right', 'left']:
        ax.spines[spine].set_visible(False)
    ax.spines['bottom'].set_color('#3d405b')
    
    # Etichette numeriche sopra le barre
    for bar in bars_a:
        yval = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width()/2.0, 
            yval + (max_val * 0.02 if max_val > 0 else 0.2), 
            f"{int(yval)}", 
            ha='center', 
            va='bottom', 
            fontsize=9, 
            fontweight='bold', 
            color='#3d405b'
        )
        
    plt.tight_layout()
    plt.savefig(path_all_time, format='png', bbox_inches='tight', transparent=False)
    plt.close()
    
    return path_month, path_all_time

def process_monthly_and_send_report(
    date_obj: datetime.date, 
    history: Dict[str, List[str]], 
    monitored_players: List[str],
    is_test: bool = False
) -> bool:
    """Genera e invia il report mensile completo con metriche e due grafici allegati su Discord."""
    logger.info("Avvio della generazione del report mensile e dei grafici...")
    
    # Recupera i mesi passati in italiano
    mesi_italiani = {
        1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile", 5: "Maggio", 6: "Giugno",
        7: "Luglio", 8: "Agosto", 9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"
    }
    
    current_month_str = f"{date_obj.year}-{date_obj.month:02d}"
    nome_mese = mesi_italiani.get(date_obj.month, f"Mese {date_obj.month}")
    
    # Se in modalità test, e il mese corrente non ha voti registrati nello storico,
    # effettua un fallback dinamico all'ultimo mese che ha dati nello storico (es. Maggio 2026)
    if is_test:
        available_months = sorted(list(set(date_key[:7] for date_key in history.keys())), reverse=True)
        current_month_votes_count = sum(1 for k in history if k.startswith(current_month_str) and history[k])
        
        if current_month_votes_count == 0 and available_months:
            for m in available_months:
                if sum(1 for k in history if k.startswith(m) and history[k]) > 0:
                    current_month_str = m
                    parts = m.split("-")
                    year = int(parts[0])
                    month_num = int(parts[1])
                    nome_mese = mesi_italiani.get(month_num, f"Mese {month_num}")
                    date_obj = datetime.date(year, month_num, 15)  # Giorno intermedio
                    logger.info(f"[TEST-FALLBACK] Nessun dato per il mese corrente. Uso il mese con storico: {nome_mese} {year} ({current_month_str})")
                    break
    
    # 1. Calcola voti del MESE CORRENTE
    month_votes = {p: 0 for p in monitored_players}
    # 2. Calcola voti ALL-TIME
    all_time_votes = {p: 0 for p in monitored_players}
    
    # Popolamento dai dati registrati nello storico
    total_days_in_month_recorded = 0
    
    for date_key, voted_list in history.items():
        # Conteggio All-Time
        for player in monitored_players:
            # Confronto case-insensitive
            voted_lower = [v.lower() for v in voted_list]
            if player.lower() in voted_lower:
                all_time_votes[player] += 1
                
        # Conteggio Mese Corrente
        if date_key.startswith(current_month_str):
            total_days_in_month_recorded += 1
            for player in monitored_players:
                voted_lower = [v.lower() for v in voted_list]
                if player.lower() in voted_lower:
                    month_votes[player] += 1
                    
    # Trova i campioni del mese (chi ha votato ogni singolo giorno registrato nel mese corrente)
    # Assumiamo una tolleranza o richiediamo il 100% dei giorni del mese di calendario
    _, days_in_month = calendar.monthrange(date_obj.year, date_obj.month)
    
    campioni = [p for p, count in month_votes.items() if count >= days_in_month]
    # Se il mese è incompleto come registrazioni, usiamo i giorni registrati effettivamente nel mese se superiori a 1
    if not campioni and total_days_in_month_recorded > 1:
        campioni = [p for p, count in month_votes.items() if count == total_days_in_month_recorded]
        
    # Formattazione delle metriche
    if campioni:
        campioni_text = ", ".join([f"🏆 **{p}**" for p in campioni])
    else:
        # In alternativa, elenca chi ha votato di più nel mese
        max_votes_m = max(month_votes.values()) if month_votes else 0
        most_active_m = [p for p, count in month_votes.items() if count == max_votes_m and count > 0]
        if most_active_m:
            campioni_text = f"Nessuno ha raggiunto il 100%, ma i più attivi sono stati: " + ", ".join([f"⭐ **{p}** ({max_votes_m} voti)" for p in most_active_m])
        else:
            campioni_text = "*Nessun voto registrato in questo mese.*"
            
    # Classifica all-time
    top_all_time = sorted(all_time_votes.items(), key=lambda x: x[1], reverse=True)
    top_all_text = "\n".join([f"🥇 **{p}** con **{count}** voti totali" if idx == 0 else
                             f"🥈 **{p}** con **{count}** voti" if idx == 1 else
                             f"🥉 **{p}** con **{count}** voti" if idx == 2 else
                             f"👤 **{p}** con **{count}** voti" 
                             for idx, (p, count) in enumerate(top_all_time[:4]) if count > 0])
    
    if not top_all_text:
        top_all_text = "*Nessun dato all-time disponibile.*"
        
    # Genera i grafici in PNG
    path_m, path_a = generate_graphics(month_votes, all_time_votes, nome_mese, date_obj.year)
    
    # Costruisce il messaggio multiparte per Discord Webhook
    payload = {
        "payload_json": json.dumps({
            "content": f"🎉 **REPORT MENSILE VOTI - {nome_mese.upper()} {date_obj.year}** 🎉\nSi è concluso un altro mese di supporto al server! Ecco i dati dettagliati.",
            "embeds": [
                {
                    "title": f"📊 Metriche e Statistiche di Fine Mese",
                    "description": f"Analisi dettagliata per il mese di **{nome_mese} {date_obj.year}**.",
                    "color": 15844367,  # Oro / Giallo brillante
                    "fields": [
                        {
                            "name": "👑 Campioni del Mese (Presenza Massima)",
                            "value": campioni_text,
                            "inline": False
                        },
                        {
                            "name": "📈 Podio Storico All-Time",
                            "value": top_all_text,
                            "inline": False
                        }
                    ],
                    "image": {
                        "url": "attachment://temp_month_votes.png"
                    },
                    "thumbnail": {
                        "url": "attachment://temp_all_time_votes.png"
                    },
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                    "footer": {
                        "text": "Made by Alessio Bellan • Elaborazione Mensile"
                    }
                }
            ]
        })
    }
    
    # Caricamento delle immagini come file binari
    files = {}
    try:
        files["files[0]"] = ("temp_month_votes.png", open(path_m, "rb"), "image/png")
        files["files[1]"] = ("temp_all_time_votes.png", open(path_a, "rb"), "image/png")
        
        success = send_discord_webhook(payload, files=files)
        if success:
            logger.info("Report mensile inviato con successo a Discord con grafici allegati.")
        else:
            logger.error("Errore nell'invio del report mensile.")
            
        return success
        
    except Exception as e:
        logger.error(f"Eccezione riscontrata durante l'elaborazione dei file del report mensile: {e}")
        return False
        
    finally:
        # Pulisce i file PNG temporanei generati per non occupare spazio inutile
        for path in [path_m, path_a]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info(f"File temporaneo rimosso: {os.path.basename(path)}")
                except Exception as e:
                    logger.warning(f"Impossibile rimuovere il file temporaneo {path}: {e}")

# ==========================================
# PUNTO DI INGRESSO PRINCIPALE (MAIN)
# ==========================================

def main():
    parser = argparse.ArgumentParser(description="Minecraft Italia Vote Monitor & Discord Webhook Reporter")
    parser.add_argument("--test", action="store_true", help="Esegue sia il test del report giornaliero reale che quello mensile con grafici.")
    parser.add_argument("--test-daily", action="store_true", help="Esegue solo il test del report giornaliero reale senza salvare nel database.")
    parser.add_argument("--test-monthly", action="store_true", help="Esegue solo il test del report mensile con grafici ed invio su Discord.")
    args = parser.parse_args()

    # Se viene richiesto un test generico, attiviamo sia il giornaliero che il mensile
    if args.test:
        args.test_daily = True
        args.test_monthly = True

    is_test_mode = args.test_daily or args.test_monthly

    if is_test_mode:
        logger.info("=== MODALITÀ DI TEST ATTIVA ===")
    else:
        logger.info("=== AVVIO SCRIP MINECRAFT ITALIA VOTE MONITOR ===")
    
    # 1. Determinazione della data odierna dello script
    today = datetime.date.today()
    date_str = today.strftime("%Y-%m-%d")
    logger.info(f"Data di esecuzione: {date_str}")
    
    # 2. Inizializzazione e caricamento dati
    monitored_players = load_players()
    if not monitored_players:
        logger.error("Nessun giocatore da monitorare trovato in players.json. Script terminato.")
        sys.exit(1)
        
    logger.info(f"Giocatori da monitorare ({len(monitored_players)}): {monitored_players}")
    
    votes_history = load_votes_history()
    
    # Esecuzione Flusso Giornaliero (standard o test)
    if not is_test_mode or args.test_daily:
        # 3. Interrogazione dell'API Minecraft Italia
        try:
            raw_votes = fetch_today_votes(SERVER_ID)
        except Exception as e:
            logger.critical(f"Lo script si interrompe a causa del fallimento della chiamata API: {e}")
            sys.exit(0)
            
        # 4. Confronto dei dati del giorno attuale
        voted_players, skipped_players = process_daily_votes(raw_votes, monitored_players)
        
        # 5. Salvataggio sicuro nello storico locale JSON (evitato nel test per non inquinare il DB)
        if not args.test_daily:
            votes_history[date_str] = voted_players
            if save_votes_history(votes_history):
                logger.info(f"Dati di voto salvati con successo nello storico per la data {date_str}.")
            else:
                logger.error("Impossibile salvare i dati nello storico. Il database potrebbe essere corrotto.")
        else:
            logger.info("[TEST-DAILY] Il salvataggio nel database storico è stato ignorato in modalità test.")
            
        # 6. Invio del report quotidiano su Discord
        if send_daily_report(date_str, voted_players, skipped_players):
            logger.info("Report quotidiano inviato con successo a Discord.")
        else:
            logger.error("Impossibile inviare il report quotidiano a Discord.")
            
    # Esecuzione Flusso Mensile (standard o test)
    if not is_test_mode:
        # standard run: trigger if today is the last day of the month
        if is_last_day_of_month(today):
            logger.info("Rilevato l'ultimo giorno del mese corrente. Avvio report mensile...")
            process_monthly_and_send_report(today, votes_history, monitored_players)
        else:
            logger.info("Oggi non è l'ultimo giorno del mese. Nessuna elaborazione mensile richiesta.")
    elif args.test_monthly:
        logger.info("[TEST-MONTHLY] Forza la generazione e l'invio del report mensile con i grafici...")
        # Usa oggi come data di riferimento per i grafici
        process_monthly_and_send_report(today, votes_history, monitored_players, is_test=True)
        
    logger.info("=== SCRIP COMPLETATO CON SUCCESSO ===")

if __name__ == "__main__":
    main()

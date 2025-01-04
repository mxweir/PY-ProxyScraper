import requests
from bs4 import BeautifulSoup
import concurrent.futures
import datetime
import random
import os
import time
from tqdm import tqdm
from fake_useragent import UserAgent
from colorama import Fore, Style, init
import json

# Initialize colorama for colored output
init(autoreset=True)

# Proxy sources
PROXY_SOURCES = {
    "1": ("Free Proxy List", "https://free-proxy-list.net/"),
    "2": ("SSL Proxies", "https://www.sslproxies.org/"),
    "3": ("Proxy List Download (HTTP)", "https://www.proxy-list.download/api/v1/get?type=http"),
    "4": ("Proxy List Download (HTTPS)", "https://www.proxy-list.download/api/v1/get?type=https"),
    "5": ("Proxy List Download (SOCKS4)", "https://www.proxy-list.download/api/v1/get?type=socks4"),
    "6": ("Proxy List Download (SOCKS5)", "https://www.proxy-list.download/api/v1/get?type=socks5"),
    "7": ("Proxyscrape (HTTP)", "https://api.proxyscrape.com/?request=getproxies&proxytype=http"),
    "8": ("Proxyscrape (SOCKS4)", "https://api.proxyscrape.com/?request=getproxies&proxytype=socks4"),
    "9": ("Proxyscrape (SOCKS5)", "https://api.proxyscrape.com/?request=getproxies&proxytype=socks5"),
    "10": ("Geonode Proxies", "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc")
}

# Test URLs
TEST_URLS = [
    "https://httpbin.org/ip",
    "https://www.google.com",
    "https://www.wikipedia.org"
]

# Timeout configuration
# Höhere Timeouts sorgen dafür, dass nicht zu viele Proxys vorschnell als "unbrauchbar" aussortiert werden.
TIMEOUT = (5, 10)  # (Connect timeout, Read timeout)

# Max threads for testing
MAX_THREADS = 20

# Randomized User-Agent for each request
ua = UserAgent()


def log_info(message):
    print(f"{Fore.GREEN}[ℹ️ INFO] {message}{Style.RESET_ALL}")

def log_warning(message):
    print(f"{Fore.YELLOW}[⚠️ WARNING] {message}{Style.RESET_ALL}")

def log_error(message):
    print(f"{Fore.RED}[❌ ERROR] {message}{Style.RESET_ALL}")

def log_success(message):
    print(f"{Fore.CYAN}[✅ SUCCESS] {message}{Style.RESET_ALL}")


def get_proxies_from_source(key):
    """
    Lädt und parst Proxys von einer einzelnen Quelle.
    Diese Funktion wird parallel von get_proxies() aufgerufen.
    """
    name, url = PROXY_SOURCES[key]
    collected = []
    log_info(f"Fetching proxies from {name} ({url})")

    try:
        headers = {"User-Agent": ua.random}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # Geonode liefert eine JSON-Antwort, also JSON parsen
        if "geonode" in url:
            data = response.json()
            if "data" in data:
                for entry in data["data"]:
                    ip = entry.get("ip", "")
                    port = entry.get("port", "")
                    # Protokoll prüfen
                    protocol_list = entry.get("protocols", [])
                    # Fallback http, wenn nichts angegeben
                    if protocol_list:
                        # Nimm am besten das erste vorhandene Protokoll oder du erweiterst die Schleife
                        protocol = protocol_list[0]
                    else:
                        protocol = "http"
                    if ip and port:
                        collected.append(f"{protocol}://{ip}:{port}")
            else:
                # Fallback: falls geonode anders reagiert
                log_warning("Geonode response has no 'data' field.")
                # Du kannst hier optional den alten Weg probieren
                # oder das Skript abbrechen.
            return collected

        # Für Proxy-Listen, die nur Rohtext liefern
        if "api/v1/get" in url or "proxyscrape.com" in url:
            collected.extend(response.text.strip().split("\n"))
            return collected

        # Standard-Fall: HTML-Parsing
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table")

        if table:
            rows = table.find_all("tr")[1:]
            for row in rows:
                cols = row.find_all("td")
                if cols:
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()
                    # Hier kannst du prüfen, ob die Spalte für HTTPS existiert:
                    if len(cols) > 6:
                        https = cols[6].text.strip().lower() == "yes"
                        protocol = "https" if https else "http"
                    else:
                        protocol = "http"
                    proxy = f"{protocol}://{ip}:{port}"
                    collected.append(proxy)

    except requests.RequestException as e:
        log_warning(f"Could not fetch proxies from {name}: {e}")

    return collected


def get_proxies(sources):
    """
    Holt die Proxys von den ausgewählten Quellen.
    Nutzt Parallelisierung für schnelleres Einlesen.
    """
    # Paralleles Abfragen der Quellen, um die Gesamt-Ladezeit zu verkürzen
    all_proxies = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(sources), 10)) as executor:
        future_to_source = {executor.submit(get_proxies_from_source, key): key for key in sources}
        for future in concurrent.futures.as_completed(future_to_source):
            source_key = future_to_source[future]
            try:
                result = future.result()
                all_proxies.extend(result)
            except Exception as exc:
                log_warning(f"Source {source_key} generated an exception: {exc}")

    # Duplikate entfernen
    all_proxies = list(set(all_proxies))

    # Eventuell schon mal mischen, um nicht in Listen-Blöcken zu testen
    random.shuffle(all_proxies)
    
    log_success(f"🔍 Found {len(all_proxies)} proxies! 🎉")
    return all_proxies


def test_proxy(proxy):
    """
    Testet einen Proxy, indem wir mehrere Webseiten prüfen.
    Anmerkung: Hier ist es so konfiguriert, dass EIN erfolgreicher Seitenaufruf ausreicht.
    Wenn du möchtest, dass ALLE URLs funktionieren müssen, passe die Logik an.
    """
    headers = {"User-Agent": ua.random}
    for url in TEST_URLS:
        try:
            response = requests.get(url, proxies={"http": proxy, "https": proxy}, headers=headers, timeout=TIMEOUT)
            # Wenn eine Seite 200 zurückgibt, akzeptieren wir den Proxy als funktionsfähig
            if response.status_code == 200:
                return proxy
        except requests.RequestException:
            # Bei Fehler: Teste die nächste URL
            continue
    # Keine URL war erfolgreich -> None
    return None


def save_proxies(proxies):
    """Speichert funktionsfähige Proxies in eine Datei mit Zeitstempel."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"WorkingProxys_{timestamp}.txt"

    with open(filename, "w") as file:
        for proxy in proxies:
            file.write(proxy + "\n")

    log_success(f"{len(proxies)} working proxies saved in {filename} 📂")


def choose_sources():
    """Ermöglicht die interaktive Auswahl der Proxy-Quellen."""
    print("Select proxy sources to use:")
    for key, (name, _) in PROXY_SOURCES.items():
        print(f" [{key}] {name}")

    print("\n [A] Select all sources")
    print(" [M] Manually select multiple sources")
    print(" [S] Select a single source")

    choice = input("\nEnter your choice: ").strip().lower()

    if choice == "a":
        return list(PROXY_SOURCES.keys())

    elif choice == "m":
        selected = input("Enter the numbers of the sources (comma-separated): ").strip()
        selected_keys = [s.strip() for s in selected.split(",")]
        valid_keys = [key for key in selected_keys if key in PROXY_SOURCES]
        if valid_keys:
            return valid_keys
        else:
            log_error("Invalid selection. Please try again.")
            return choose_sources()

    elif choice == "s":
        selected = input("Enter the number of the source: ").strip()
        if selected in PROXY_SOURCES:
            return [selected]
        else:
            log_error("Invalid selection. Please try again.")
            return choose_sources()
    else:
        log_error("Invalid choice. Please try again.")
        return choose_sources()


def main():
    log_info("🚀 Proxy Scraper & Tester started!")
    sources = choose_sources()

    proxies = get_proxies(sources)
    if not proxies:
        log_error("No proxies found. Exiting. ❌")
        return

    log_info(f"⏳ Testing {len(proxies)} proxies with {MAX_THREADS} threads...")

    # Proxy-Check mit ThreadPoolExecutor
    working_proxies = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        results = list(tqdm(executor.map(test_proxy, proxies), total=len(proxies), desc="Testing Proxies"))

    working_proxies = [proxy for proxy in results if proxy]

    if working_proxies:
        save_proxies(working_proxies)
    else:
        log_warning("No working proxies found. 😔")

    log_info("🎉 Proxy check completed!")


if __name__ == "__main__":
    main()

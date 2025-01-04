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
    Gibt eine Liste von Dictionaries zurück, z.B.:
    [
      {
        "ip": "1.2.3.4",
        "port": "8080",
        "protocol": "http"|"https"|"socks4"|"socks5",
        "country": "US"
      },
      ...
    ]
    """
    name, url = PROXY_SOURCES[key]
    proxy_dicts = []
    log_info(f"Fetching proxies from {name} ({url})")

    try:
        headers = {"User-Agent": ua.random}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # ============== Geonode (JSON) ==============
        if "geonode" in url:
            data = response.json()
            if "data" in data:
                for entry in data["data"]:
                    ip = entry.get("ip", "").strip()
                    port = str(entry.get("port", "")).strip()
                    protocol_list = entry.get("protocols", [])
                    country_code = entry.get("country", "??").strip()  # z.B. "US"

                    # Falls Protokoll unklar, Standard = http
                    protocol = protocol_list[0] if protocol_list else "http"

                    if ip and port:
                        proxy_dicts.append({
                            "ip": ip,
                            "port": port,
                            "protocol": protocol,
                            "country": country_code
                        })
            else:
                log_warning("Geonode response has no 'data' field.")
            return proxy_dicts

        # ============== API/Plain Text ==============
        if "api/v1/get" in url or "proxyscrape.com" in url:
            # Hier gibt's nur IP:Port => Kein Country-Code, Protokoll unbekannt => Standard = http
            lines = response.text.strip().split("\n")
            for line in lines:
                line = line.strip()
                if ":" in line:
                    ip_port = line.split(":")
                    if len(ip_port) == 2:
                        ip, port = ip_port
                        proxy_dicts.append({
                            "ip": ip.strip(),
                            "port": port.strip(),
                            "protocol": "http",  # oder "socks4"/"socks5" - hier bräuchte man Parser-Logik
                            "country": "??"
                        })
            return proxy_dicts

        # ============== HTML-Parsing (Tabellen) ==============
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table")

        if table:
            rows = table.find_all("tr")[1:]  # Erste Zeile ist Header
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 2:
                    # IP und Port
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()

                    # Sofern vorhanden: Spalte 2 => Landeskürzel (Code)
                    if len(cols) >= 3:
                        country_code = cols[2].text.strip()
                    else:
                        country_code = "??"

                    # Spalte 6 oder 7 => HTTPS 'yes'/'no' => muss je nach Quelle geprüft werden
                    # Free-proxy-list hat das in Spalte 6
                    # SSL-Proxies hat das in Spalte 6
                    https_col_index = 6  # kann je nach HTML abweichen
                    if len(cols) > https_col_index:
                        https_flag = cols[https_col_index].text.strip().lower() == "yes"
                        protocol = "https" if https_flag else "http"
                    else:
                        protocol = "http"

                    proxy_dicts.append({
                        "ip": ip,
                        "port": port,
                        "protocol": protocol,
                        "country": country_code
                    })
    except requests.RequestException as e:
        log_warning(f"Could not fetch proxies from {name}: {e}")

    return proxy_dicts


def get_proxies(sources):
    """
    Holt die Proxys von den ausgewählten Quellen (parallel).
    Gibt eine Liste von Dictionaries zurück.
    """
    all_proxies = []

    # Parallelisieren, um schneller alle Quellen abzufragen
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(sources), 10)) as executor:
        future_to_source = {executor.submit(get_proxies_from_source, key): key for key in sources}
        for future in concurrent.futures.as_completed(future_to_source):
            source_key = future_to_source[future]
            try:
                result = future.result()
                all_proxies.extend(result)
            except Exception as exc:
                log_warning(f"Source {source_key} generated an exception: {exc}")

    # Duplikate entfernen:
    # Da es jetzt Dictionaries sind, müssen wir sie in ein "hashbares" Format wandeln
    # (z.B. tuple), um Duplikate rauszufiltern.
    unique_set = set()
    unique_proxies = []
    for prx in all_proxies:
        # Erstelle ein Tuple (ip, port, protocol, country)
        prx_tuple = (prx["ip"], prx["port"], prx["protocol"], prx["country"])
        if prx_tuple not in unique_set:
            unique_set.add(prx_tuple)
            unique_proxies.append(prx)

    # Für besseren Proxy-Mix:
    random.shuffle(unique_proxies)

    log_success(f"🔍 Found {len(unique_proxies)} proxies! 🎉")
    return unique_proxies


def test_proxy(proxy_dict):
    """
    Testet einen Proxy mit mehreren URLs.
    proxy_dict = {"ip":..., "port":..., "protocol":..., "country":...}
    Gibt das Dictionary zurück, wenn erfolgreich, sonst None.
    
    Hinweis: Wir akzeptieren den Proxy schon, 
    wenn ER EINE der Test-URLs erfolgreich aufrufen kann.
    """
    proxy_str = f"{proxy_dict['protocol']}://{proxy_dict['ip']}:{proxy_dict['port']}"
    headers = {"User-Agent": ua.random}

    for url in TEST_URLS:
        try:
            response = requests.get(
                url,
                proxies={"http": proxy_str, "https": proxy_str},
                headers=headers,
                timeout=TIMEOUT
            )
            # Bei erstem Erfolg beenden
            if response.status_code == 200:
                return proxy_dict
        except requests.RequestException:
            continue

    return None


def save_proxies(proxy_list):
    """
    Speichert funktionsfähige Proxies in eine Datei mit Zeitstempel.
    Format pro Zeile:
    <protokoll>://<ip>:<port> <country_code>
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"WorkingProxys_{timestamp}.txt"

    with open(filename, "w") as file:
        for prx in proxy_list:
            line = f"{prx['protocol']}://{prx['ip']}:{prx['port']} {prx['country']}"
            file.write(line + "\n")

    log_success(f"{len(proxy_list)} working proxies saved in {filename} 📂")


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

    proxy_list = get_proxies(sources)
    if not proxy_list:
        log_error("No proxies found. Exiting. ❌")
        return

    log_info(f"⏳ Testing {len(proxy_list)} proxies with {MAX_THREADS} threads...")

    # Proxy-Check mit ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        results = list(tqdm(executor.map(test_proxy, proxy_list), total=len(proxy_list), desc="Testing Proxies"))

    # Nur die Proxies behalten, die nicht None sind
    working_proxies = [prx for prx in results if prx]

    if working_proxies:
        save_proxies(working_proxies)
    else:
        log_warning("No working proxies found. 😔")

    log_info("🎉 Proxy check completed!")


if __name__ == "__main__":
    main()

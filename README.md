# PY-ProxyScraper

A Python-based proxy scraper and tester that retrieves proxies from multiple sources, checks their functionality, and saves working proxies with protocol and country code.

## Features

- **Multi-Source Scraping**: Fetch proxies from various sources (e.g., free-proxy-list.net, sslproxies.org, proxy-list.download, Proxyscrape, Geonode, etc.).
- **Parallel Fetching**: Scrape proxies in parallel for faster overall performance.
- **Proxy Validation**: Test each proxy against multiple URLs (e.g., [httpbin.org/ip](https://httpbin.org/ip), [google.com](https://www.google.com), [wikipedia.org](https://www.wikipedia.org)).
- **Country Code Detection**: Parse the country code (if available) from the proxy source or use default `??` if no data is provided.
- **Saving Results**: All working proxies are saved in a time-stamped file, each line containing `<protocol>://<ip>:<port> <country>`.

## Requirements

- Python 3.7+
- `requests`
- `beautifulsoup4`
- `fake_useragent`
- `tqdm`
- `colorama`

You can install all required packages via:

```bash
pip install -r requirements.txt

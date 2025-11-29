# ContactHarvest

ContactHarvest is an advanced asynchronous web crawler designed to extract contact information from websites, including emails, phone numbers, social media links, and metadata.

---

## Features

- **Asynchronous crawling** with `aiohttp` for high performance
- **Follow HTTP redirects** to get the final page URL  
- **Recursive crawling** of internal pages
- **Extract emails** from text content and mailto links
- **Detect phone numbers** in various international formats
- **Social media extraction** (LinkedIn, Twitter/X, Facebook, Instagram, GitHub, YouTube)
- **Metadata extraction** (page title, description, generator)
- **User-Agent rotation** to avoid blocking
- **Proxy support** for anonymous crawling
- **Rich CLI output** with progress bars and formatted tables
- **Export results** to JSON or CSV
- **Configurable parameters** (max pages, timeout, delay)

---

## Installation

### Using `virtualenv` (recommended)

1. Install `virtualenv` if necessary:

```bash
pip install virtualenv
```

2. Create and activate a new virtual environment:

```bash
virtualenv contactharvest-env
source contactharvest-env/bin/activate  # On Windows: contactharvest-env\Scripts\activate
```

3. Install ContactHarvest:

```bash
pip install -r requirements.txt
```

---

## Usage

### Command-line Interface (CLI)

```bash
python contactharvest/cli.py <url>
```

Example:

```bash
python contactharvest/cli.py https://example.com
```

**Available options:**
- `--max-pages`, `-mp`: Maximum number of pages to crawl (default: 50)
- `--timeout`, `-t`: Request timeout in seconds (default: 30)
- `--delay`, `-d`: Delay between requests in seconds (default: 1.0)
- `--verbose`, `-v`: Print every page being searched
- `--recursive`, `-r`: Follow every internal link
- `--verify_ssl`, `-vssl`: Verify SSL certificates
- `--proxy`, `-p`: Proxy URL (e.g., http://user:pass@host:port)
- `--output`, `-o`: Output file path (.json or .csv)

**Examples:**

```bash
# Basic crawl with JSON export
python contactharvest/cli.py https://example.com -o results.json

# Recursive crawl with proxy
python contactharvest/cli.py https://example.com -r --proxy http://proxy:8080

# Verbose crawl with custom parameters
python contactharvest/cli.py https://example.com -v --max-pages 100 --delay 2.0
```

---

### Python Module

```python
import asyncio
from contactharvest import Crawler

async def main():
    # Create a crawler instance
    async with Crawler(
        url="https://example.com",
        max_pages=50,
        timeout=30,
        delay=1.0,
        verbose=True,
        recursive=True
    ) as crawler:
        # Fetch the URL and follow redirects
        await crawler.fetch()
        print(f"Final URL: {crawler.final_url}")
        
        # Extract all information
        await crawler.extract_emails()
        
        # Get results
        results = crawler.get_results()
        
        # Process results
        for item in results:
            print(f"{item.type}: {item.value}")
            if item.source_url:
                print(f"  Found on: {item.source_url}")

# Run the async function
asyncio.run(main())
```

---

## Dependencies

* Python 3.7+
* aiohttp
* beautifulsoup4
* lxml
* rich
* fake-useragent

These dependencies are automatically installed via `pip` when you install the package.

---

## Development

* Core code is in the `contactharvest/` package
* CLI script is in `contactharvest/cli.py`
* Tests can be run with: `python -m pytest tests/`

---

## License

[MIT License](LICENSE)
import asyncio
import aiohttp
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import List, Set, Dict, Optional
from dataclasses import dataclass
import time
import logging
from fake_useragent import UserAgent

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

@dataclass
class TrackingItem:
    """Represents a found tracking item (email, phone, social, metadata)."""
    type: str
    value: str
    source_url: str = ""
    metadata: Optional[Dict] = None


class Crawler:
    """A web crawler that extracts emails and phone numbers from websites."""
    
    def __init__(self, url: str, max_pages: int = 50, timeout: int = 30, delay: float = 1.0, verbose: bool = False, recursive: bool = False, verify_ssl: bool = True, proxy: str = None):
        """
        Initialize the crawler.
        
        Args:
            url: The URL to crawl
            max_pages: Maximum number of pages to crawl
            timeout: Request timeout in seconds
            delay: Delay between requests in seconds
            verbose: Print every page being searched
            recursive: Follow every internal link (default: only crawl the final page after redirects)
            verify_ssl: Whether to verify SSL certificates (default: True)
            proxy: Proxy URL (e.g., http://user:pass@host:port)
        """
        self.url = url
        self.max_pages = max_pages
        self.timeout = timeout
        self.delay = delay
        self.verbose = verbose
        self.recursive = recursive
        self.verify_ssl = verify_ssl
        self.proxy = proxy
        self.final_url = url
        self.visited_urls: Set[str] = set()  # Stores normalized URLs to prevent duplicate visits
        self.results: List[TrackingItem] = []
        self._seen_values: Set[str] = set()  # Track seen values to prevent duplicates
        self.session: Optional[aiohttp.ClientSession] = None
        self.ua = UserAgent()
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=self.verify_ssl))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication by removing fragments, query params, and trailing slashes."""
        try:
            parsed = urlparse(url)
            # Remove fragment and query parameters
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            # Remove trailing slash except for root path
            if normalized.endswith('/') and len(normalized) > len(f"{parsed.scheme}://{parsed.netloc}"):
                normalized = normalized.rstrip('/')
            return normalized.lower()
        except Exception:
            return url.lower()

    def _is_duplicate(self, item_type: str, value: str) -> bool:
        """Check if a value has already been seen (case-insensitive for emails, normalized for phones)."""
        # For emails, normalize to lowercase for comparison
        if item_type == "email":
            normalized_value = value.lower()
        else:
            # For phones, normalize by removing all non-digit characters
            normalized_value = self._normalize_phone_for_dedup(value)
        
        return normalized_value in self._seen_values
    
    def _add_result(self, item_type: str, value: str, source_url: str):
        """Add a result if it's not a duplicate."""
        if not self._is_duplicate(item_type, value):
            # For emails, normalize to lowercase for tracking
            if item_type == "email":
                self._seen_values.add(value.lower())
            else:
                # For phones, normalize by removing all non-digit characters
                self._seen_values.add(self._normalize_phone_for_dedup(value))
            
            self.results.append(TrackingItem(
                type=item_type,
                value=value,
                source_url=source_url
            ))
    
    def _ensure_protocol(self, url: str) -> str:
        """Ensure URL has a protocol."""
        if not url.startswith(('http://', 'https://')):
            return 'https://' + url
        return url
    
    async def _get_final_url(self, url: str) -> str:
        """Follow redirects to get the final URL."""
        if not self.session:
             self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=self.verify_ssl))

        headers = {'User-Agent': self.ua.random}
        try:
            async with self.session.head(url, timeout=self.timeout, allow_redirects=True, headers=headers, proxy=self.proxy) as response:
                return str(response.url)
        except Exception:
            # Fallback to GET if HEAD fails
            try:
                async with self.session.get(url, timeout=self.timeout, allow_redirects=True, headers=headers, proxy=self.proxy) as response:
                    return str(response.url)
            except Exception:
                return url
    
    def _is_same_domain(self, url: str, base_domain: str) -> bool:
        """Check if URL belongs to the same domain."""
        try:
            parsed_url = urlparse(url)
            parsed_base = urlparse(base_domain)
            return parsed_url.netloc == parsed_base.netloc
        except Exception:
            return False
    
    def _extract_internal_links(self, soup: BeautifulSoup, base_url: str) -> Set[str]:
        """Extract internal links from the page."""
        internal_links = set()
        
        try:
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                if not href:
                    continue
                    
                # Resolve relative URLs
                absolute_url = urljoin(base_url, href)
                
                # Normalize URL for deduplication
                normalized_url = self._normalize_url(absolute_url)
                
                # Check if it's an internal link and not already visited (using normalized URL)
                if self._is_same_domain(absolute_url, base_url) and normalized_url not in self.visited_urls:
                    # Filter out common non-content URLs
                    if not any(exclude in absolute_url.lower() for exclude in [
                        '#', 'javascript:', 'mailto:', 'tel:', '.pdf', '.doc', '.docx', 
                        '.jpg', '.jpeg', '.png', '.gif', '.css', '.js', '.xml', '.rss',
                        'logout', 'admin', 'login', 'register', 'signup', 'signin'
                    ]):
                        internal_links.add(absolute_url)
                        
        except Exception:
            pass
            
        return internal_links
    
    def _extract_emails_from_text(self, text: str) -> List[str]:
        """Extract emails from text content."""
        try:
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
            emails = re.findall(email_pattern, text)
            # Remove duplicates while preserving order
            return list(dict.fromkeys(emails))
        except Exception:
            return []
    
    def _extract_emails_from_mailto(self, html: str) -> List[str]:
        """Extract emails from mailto links in HTML content."""
        try:
            emails = []
            
            # Extract mailto patterns from the entire content
            mailto_pattern = r'mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})'
            mailto_matches = re.findall(mailto_pattern, html, re.IGNORECASE)
            for email in mailto_matches:
                email_clean = email.strip()
                if len(email_clean) <= 100:
                    emails.append(email_clean)
            
            # If it looks like HTML, also try to parse it with BeautifulSoup
            if '<' in html and '>' in html:
                try:
                    soup = BeautifulSoup(html, 'html.parser')
                    mailto_links = soup.find_all('a', href=re.compile(r'^mailto:', re.IGNORECASE))
                    
                    for link in mailto_links:
                        href = link.get('href', '')
                        email_match = re.search(r'^mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', href, re.IGNORECASE)
                        if email_match:
                            email = email_match.group(1).strip()
                            if len(email) <= 100:
                                emails.append(email)
                except Exception:
                    pass
            
            # Remove duplicates while preserving order
            return list(dict.fromkeys(emails))
            
        except Exception:
            return []
    
    def _clean_international_phone(self, phone: str) -> str:
        """Clean and standardize international phone number format."""
        try:
            # Remove extra whitespace
            phone = re.sub(r'\s+', ' ', phone.strip())
            # Normalize separators - replace dashes, dots, and multiple spaces with a single space
            phone = re.sub(r'[-.]+', ' ', phone)
            phone = re.sub(r'\s+', ' ', phone)
            # Remove parentheses but keep the content
            phone = re.sub(r'[()]', '', phone)
            # Clean up any remaining extra spaces
            phone = re.sub(r'\s+', ' ', phone).strip()
            return phone
        except Exception:
            return phone

    def _normalize_phone_for_dedup(self, phone: str) -> str:
        """Normalize phone number for deduplication by removing all non-digit characters."""
        try:
            # Remove all non-digit characters for comparison
            digits_only = re.sub(r'[^\d]', '', phone)
            return digits_only
        except Exception:
            return phone

    def _extract_phones(self, text: str) -> List[str]:
        """Extract phone numbers from text content."""
        try:
            phones = []
            # Patterns for US and international numbers
            patterns = [
                # US phone numbers with country code
                r'\b\+1[-.\s]?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b',
                # US phone numbers without country code (but with context)
                r'\b\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b',
                # International format: +country (area) xx xx xx ...
                r'\+(\d{1,4})[\s.-]?(\(?\d{1,4}\)?[\s.-]?){2,6}\d{2,4}\b',
            ]
            for idx, pattern in enumerate(patterns):
                for match_obj in re.finditer(pattern, text, re.IGNORECASE):
                    original_match = match_obj.group(0)
                    if self._is_valid_phone(original_match, text):
                        if idx == 0:  # US with country code
                            groups = match_obj.groups()
                            if len(groups) == 3:
                                phone = f"+1-{groups[0]}-{groups[1]}-{groups[2]}"
                            else:
                                phone = original_match
                        elif idx == 1:  # US without country code
                            groups = match_obj.groups()
                            if len(groups) == 3:
                                phone = f"+1-{groups[0]}-{groups[1]}-{groups[2]}"
                            else:
                                phone = original_match
                        else:  # International
                            phone = self._clean_international_phone(original_match)
                        phones.append(phone)
            return list(dict.fromkeys(phones))
        except Exception:
            return []
    
    def _is_valid_phone(self, phone: str, context: str = "") -> bool:
        """Validate if a phone number is reasonable."""
        try:
            # Remove common separators and get just digits
            digits = re.sub(r'[^\d]', '', phone)
            # Must have 10-15 digits (reasonable for phone numbers)
            if len(digits) < 10 or len(digits) > 15:
                return False
            # Reject if the phone value is just a sequence of digits (no separators)
            if re.fullmatch(r'\d{10,15}', phone):
                return False
            # Require at least one separator (space, dash, dot, parenthesis, or plus)
            if not re.search(r'[\s\-\.\(\)\+]', phone):
                return False
            # For international numbers, require at least one separator after the country code
            if phone.startswith('+'):
                # Remove the country code
                m = re.match(r'(\+\d{1,4})(.*)', phone)
                if m:
                    after_cc = m.group(2)
                    # There must be at least one separator in the rest of the number
                    if not re.search(r'[\s\-\.\(\)]', after_cc):
                        return False
            return True
        except Exception:
            return False

    def _extract_social_media(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract social media links."""
        social_links = []
        platforms = {
            'linkedin': r'linkedin\.com/in/|linkedin\.com/company/',
            'twitter': r'twitter\.com/|x\.com/',
            'facebook': r'facebook\.com/',
            'instagram': r'instagram\.com/',
            'github': r'github\.com/',
            'youtube': r'youtube\.com/',
        }
        
        try:
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                for platform, pattern in platforms.items():
                    if re.search(pattern, href, re.IGNORECASE):
                        social_links.append({'platform': platform, 'url': href})
                        break
            return social_links
        except Exception:
            return []

    def _extract_metadata(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract page metadata."""
        metadata = {}
        try:
            if soup.title:
                metadata['title'] = soup.title.string.strip()
            
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                metadata['description'] = meta_desc.get('content', '').strip()
                
            meta_gen = soup.find('meta', attrs={'name': 'generator'})
            if meta_gen:
                metadata['generator'] = meta_gen.get('content', '').strip()
                
            return metadata
        except Exception:
            return metadata
    
    async def _process_page(self, url: str) -> Dict[str, List[str]]:
        """Process a single page and extract emails and phones."""
        try:
            # Add delay to be respectful to the server
            if len(self.visited_urls) > 0:
                await asyncio.sleep(self.delay)
            
            if self.verbose:
                logger.info(f"Searching: {url}")
            
            headers = {'User-Agent': self.ua.random}

            # HEAD request optimization: Check Content-Type first
            try:
                async with self.session.head(url, timeout=self.timeout, headers=headers, proxy=self.proxy) as response:
                    content_type = response.headers.get('Content-Type', '').lower()
                    if 'text/html' not in content_type:
                        if self.verbose:
                            logger.info(f"Skipping {url}: Content-Type is {content_type}")
                        return {"emails": [], "phones": [], "internal_links": set(), "social": [], "metadata": {}}
            except Exception:
                pass # Ignore HEAD errors and try GET

            # Get the page
            async with self.session.get(url, timeout=self.timeout, headers=headers, proxy=self.proxy) as response:
                # Only proceed if we get a 200 status code
                if response.status != 200:
                    if self.verbose:
                        logger.info(f"❌ Skipping {url}: HTTP {response.status}")
                    return {"emails": [], "phones": [], "internal_links": set(), "social": [], "metadata": {}}
                
                # Parse HTML content
                html_content = await response.text()
                soup = BeautifulSoup(html_content, 'html.parser')
                visible_text = soup.get_text(separator=' ')
                
                # Extract emails from both HTML content and visible text
                emails_from_text = self._extract_emails_from_text(visible_text)
                emails_from_mailto = self._extract_emails_from_mailto(html_content)
                all_emails = list(dict.fromkeys(emails_from_text + emails_from_mailto))
                
                # Extract phone numbers
                phones = self._extract_phones(visible_text)
                
                # Extract social media
                social_links = self._extract_social_media(soup)
                
                # Extract metadata
                metadata = self._extract_metadata(soup)
                
                # Extract internal links
                internal_links = self._extract_internal_links(soup, url)

                if self.verbose and (all_emails or phones or social_links):
                    logger.info(f"✅ Found on {url}: {len(all_emails)} emails, {len(phones)} phones, {len(social_links)} social links")
                
                return {
                    "emails": all_emails,
                    "phones": phones,
                    "internal_links": internal_links,
                    "social": social_links,
                    "metadata": metadata
                }
            
        except Exception as e:
            if self.verbose:
                logger.error(f"❌ Error processing {url}: {str(e)}")
            return {"emails": [], "phones": [], "internal_links": set(), "social": [], "metadata": {}}
    
    async def fetch(self):
        """Fetch the initial URL and follow redirects."""
        try:
            # Ensure URL has protocol
            self.url = self._ensure_protocol(self.url)
            
            # Get final URL after redirects
            self.final_url = await self._get_final_url(self.url)
            
        except Exception as e:
            raise RuntimeError(f"Failed to fetch URL: {str(e)}")
    
    async def extract_emails(self):
        """Extract emails from the website."""
        await self._crawl_and_extract()
    
    async def extract_phones(self):
        """Extract phone numbers from the website."""
        # This is handled in _crawl_and_extract, but we keep the method for API consistency
        pass
    
    async def _crawl_and_extract(self):
        """Crawl the website and extract emails and phone numbers."""
        if not self.final_url:
            raise RuntimeError("Must call fetch() before extracting data")
        
        if not self.session:
             self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=self.verify_ssl))

        try:
            if self.recursive:
                # Recursive mode: crawl multiple pages
                urls_to_visit = {self.final_url}
                page_count = 0
                
                while urls_to_visit and page_count < self.max_pages:
                    current_url = urls_to_visit.pop()
                    
                    # Normalize URL for deduplication
                    normalized_url = self._normalize_url(current_url)
                    
                    if normalized_url in self.visited_urls:
                        continue
                        
                    self.visited_urls.add(normalized_url)
                    page_count += 1
                    
                    # Process the page
                    page_data = await self._process_page(current_url)
                    
                    # Add emails to results
                    for email in page_data["emails"]:
                        self._add_result("email", email, current_url)
                    
                    # Add phones to results
                    for phone in page_data["phones"]:
                        self._add_result("phone", phone, current_url)
                    
                    # Add social links to results
                    for social in page_data["social"]:
                         self._add_result("social", social['url'], current_url)
                    
                    # Add metadata to results
                    if page_data["metadata"]:
                        self._add_result("metadata", str(page_data["metadata"]), current_url)

                    # Add new links to visit
                    if page_count < self.max_pages:
                        urls_to_visit.update(page_data["internal_links"])
            else:
                # Non-recursive mode: only crawl the final page
                normalized_url = self._normalize_url(self.final_url)
                self.visited_urls.add(normalized_url)
                page_data = await self._process_page(self.final_url)
                
                # Add emails to results
                for email in page_data["emails"]:
                    self._add_result("email", email, self.final_url)
                
                # Add phones to results
                for phone in page_data["phones"]:
                    self._add_result("phone", phone, self.final_url)
                
                # Add social links to results
                for social in page_data["social"]:
                        self._add_result("social", social['url'], self.final_url)
                
                # Add metadata
                if page_data["metadata"]:
                    self._add_result("metadata", str(page_data["metadata"]), self.final_url)
        finally:
            # Close session if we created it here (though usually managed by context manager)
            pass

    def get_results(self) -> List[TrackingItem]:
        """Get the extracted results (already deduplicated)."""
        return self.results

    def get_deduplicated_results(self) -> List[TrackingItem]:
        """Get the extracted results with duplicates removed (alias for get_results)."""
        return self.results
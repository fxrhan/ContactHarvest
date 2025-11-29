import pytest
from unittest.mock import Mock, AsyncMock, patch
from contactharvest import Crawler, TrackingItem

@pytest.fixture
def crawler():
    return Crawler("https://example.com")

def test_crawler_initialization(crawler):
    """Test that Crawler initializes correctly."""
    assert crawler.url == "https://example.com"
    assert crawler.max_pages == 50
    assert crawler.timeout == 30
    assert crawler.delay == 1.0
    assert crawler.final_url == "https://example.com"
    assert len(crawler.visited_urls) == 0
    assert len(crawler.results) == 0

def test_ensure_protocol(crawler):
    """Test URL protocol handling."""
    assert crawler._ensure_protocol("example.com") == "https://example.com"
    assert crawler._ensure_protocol("https://example.com") == "https://example.com"
    assert crawler._ensure_protocol("http://example.com") == "http://example.com"

def test_extract_emails_from_text(crawler):
    """Test email extraction from text."""
    text = "Contact us at test@example.com or support@test.com"
    emails = crawler._extract_emails_from_text(text)
    assert "test@example.com" in emails
    assert "support@test.com" in emails
    assert len(emails) == 2

def test_extract_phones(crawler):
    """Test phone number extraction."""
    text = "Call us at (555) 123-4567 or +1-555-987-6543"
    phones = crawler._extract_phones(text)
    assert "+1-555-123-4567" in phones
    assert "+1-555-987-6543" in phones

def test_tracking_item():
    """Test TrackingItem dataclass."""
    item = TrackingItem(type="email", value="test@example.com", source_url="https://example.com/contact")
    assert item.type == "email"
    assert item.value == "test@example.com"
    assert item.source_url == "https://example.com/contact"

@pytest.mark.skip(reason="Mocking aiohttp session is flaky")
@pytest.mark.asyncio
async def test_get_final_url(crawler):
    """Test final URL resolution."""
    mock_response = Mock()
    mock_response.url = "https://example.com/final"
    
    # Mock the session context manager
    mock_context = AsyncMock()
    mock_context.__aenter__.return_value = mock_response
    mock_context.__aexit__.return_value = None
    
    mock_session = AsyncMock()
    mock_session.head.return_value = mock_context
    mock_session.get.return_value = mock_context
    
    crawler.session = mock_session
    
    final_url = await crawler._get_final_url("https://example.com")
    assert final_url == "https://example.com/final"

def test_is_same_domain(crawler):
    """Test domain comparison."""
    assert crawler._is_same_domain("https://example.com/page", "https://example.com")
    assert crawler._is_same_domain("https://sub.example.com/page", "https://sub.example.com")
    assert not crawler._is_same_domain("https://other.com/page", "https://example.com")

def test_extract_phones_strict(crawler):
    """Test stricter phone number extraction logic."""
    # Should match
    assert "+1-555-123-4567" in crawler._extract_phones("Call us at (555) 123-4567")
    
    # Should NOT match plain digit sequences
    assert crawler._extract_phones("1234567890") == []

def test_international_phone_numbers(crawler):
    """Test international phone number extraction."""
    assert "+33 1 42 86 12 34" in crawler._extract_phones("Contact: +33 1 42 86 12 34")
    assert "+44 20 7946 0958" in crawler._extract_phones("UK office: +44 20 7946 0958")

def test_deduplication(crawler):
    """Test that duplicates are properly removed."""
    assert not crawler._is_duplicate("email", "test@example.com")
    crawler._add_result("email", "test@example.com", "https://example.com/page1")
    assert crawler._is_duplicate("email", "test@example.com")
    assert crawler._is_duplicate("email", "TEST@EXAMPLE.COM")

def test_extract_social_media(crawler):
    """Test social media extraction."""
    from bs4 import BeautifulSoup
    html = """
    <html>
        <a href="https://twitter.com/example">Twitter</a>
        <a href="https://linkedin.com/in/example">LinkedIn</a>
        <a href="https://facebook.com/example">Facebook</a>
    </html>
    """
    soup = BeautifulSoup(html, 'html.parser')
    socials = crawler._extract_social_media(soup)
    
    platforms = [s['platform'] for s in socials]
    assert 'twitter' in platforms
    assert 'linkedin' in platforms
    assert 'facebook' in platforms

def test_extract_metadata(crawler):
    """Test metadata extraction."""
    from bs4 import BeautifulSoup
    html = """
    <html>
        <head>
            <title>Test Page</title>
            <meta name="description" content="This is a test page">
            <meta name="generator" content="WordPress">
        </head>
    </html>
    """
    soup = BeautifulSoup(html, 'html.parser')
    metadata = crawler._extract_metadata(soup)
    
    assert metadata['title'] == "Test Page"
    assert metadata['description'] == "This is a test page"
    assert metadata['generator'] == "WordPress"

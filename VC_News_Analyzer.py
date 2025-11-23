"""
VC & Startup News Analyzer
Fetches VC and startup news from multiple sources, analyzes with Google Gemini 2.5 Flash,
and sends opportunities to Telegram.
"""

import feedparser
import requests
import time
import schedule
from datetime import datetime, timedelta
from typing import List, Dict, Any, Set, Optional
import os
import json
import hashlib
import random
import logging
import sys
import traceback
from functools import wraps
import signal
import google.generativeai as genai
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('vc_news_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def timeout_handler(signum, frame):
    """Handler for timeout signal"""
    raise TimeoutError("Operation timed out")


def with_timeout(timeout_seconds=15):
    """Decorator to add timeout to a function"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Set the signal handler and alarm
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)
            try:
                result = func(*args, **kwargs)
            finally:
                # Disable the alarm and restore old handler
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
            return result
        return wrapper
    return decorator


def retry_on_failure(max_retries=3, delay=5, backoff=2):
    """Decorator to retry a function on failure with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            current_delay = delay
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries >= max_retries:
                        logger.error(f"{func.__name__} failed after {max_retries} retries: {str(e)}")
                        raise
                    logger.warning(f"{func.__name__} failed (attempt {retries}/{max_retries}): {str(e)}. Retrying in {current_delay}s...")
                    time.sleep(current_delay)
                    current_delay *= backoff
            return None
        return wrapper
    return decorator


class VCNewsAnalyzer:
    def __init__(self):
        # API Keys - Set these as environment variables
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        # Configure Gemini
        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
            self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        # RSS Feed URLs
        self.rss_feeds = {
            'Crunchbase News': 'https://news.crunchbase.com/feed/',
            'Above the Crowd': 'https://abovethecrowd.com/feed/',
            'TechCrunch Startups': 'https://techcrunch.com/tag/startups/feed/',
            'VentureBeat': 'https://venturebeat.com/feed',
            'For Entrepreneurs': 'https://forentrepreneurs.com/blog/feed/',
            'VC Cafe': 'https://vccafe.com/feed',
            'This is going to be BIG': 'https://feeds.feedburner.com/thisisgoingtobebig',
            'Strictly Business Law Blog': 'https://www.strictlybusinesslawblog.com/feed/',
            'Both Sides of the Table': 'https://feeds.feedburner.com/Bothsidesofthetable',
            'Neil Patel': 'https://neilpatel.com/feed/'
        }
        
        # History tracking file
        self.history_file = 'sent_news_history.json'
        self.sent_news_hashes = self._load_history()
        
        # Load prompt variations
        self.prompts = self._load_prompts()
        self.current_prompt_style = None  # Will be set during analysis
        
        # Load message templates
        self.message_templates = self._load_message_templates()
    
    def _load_prompts(self) -> Dict[str, Dict[str, str]]:
        """Load prompt variations from prompts.json"""
        try:
            with open('prompts.json', 'r') as f:
                prompts = json.load(f)
                print(f"📝 Loaded {len(prompts)} prompt variations")
                return prompts
        except FileNotFoundError:
            print("⚠ prompts.json not found, using default prompt")
            return {
                "original": {
                    "prompt": "Analyze the following VC and startup news items and identify potential investment or business opportunities.\n\nFor each item, determine:\n1. Is this a significant opportunity? (YES/NO)\n2. What type of opportunity? (funding round, new startup launch, market trend, technology breakthrough, partnership, acquisition, IPO, etc.)\n3. Risk level (LOW/MEDIUM/HIGH)\n4. Brief explanation (max 2 sentences)\n\nContent to analyze:\n{content_summary}\n\nRespond in JSON format for each item:\n{{\n    \"item_1\": {{\n        \"is_opportunity\": true/false,\n        \"opportunity_type\": \"type\",\n        \"risk_level\": \"LOW/MEDIUM/HIGH\",\n        \"explanation\": \"brief explanation\"\n    }},\n    ...\n}}",
                    "emoji": "�"
                }
            }
        except Exception as e:
            print(f"⚠ Error loading prompts: {str(e)}")
            return {}
    
    def _load_message_templates(self) -> Dict[str, Dict[str, str]]:
        """Load message templates from message_templates.json"""
        try:
            with open('message_templates.json', 'r') as f:
                templates = json.load(f)
                print(f"💬 Loaded {len(templates)} message templates")
                return templates
        except FileNotFoundError:
            print("⚠ message_templates.json not found, using default template")
            return {
                "original": {
                    "template": "{emoji} *VC/Startup Opportunity Detected*\n\n*Source:* {source}\n*Title:* {title}\n\n*Type:* {opportunity_type}\n*Risk Level:* {risk_level}\n\n*Analysis:*\n{explanation}\n\n*Link:* {link}\n\n_Analyzed at {timestamp}_\n_Style: {style}_"
                }
            }
        except Exception as e:
            print(f"⚠ Error loading message templates: {str(e)}")
            return {}
    
    def _generate_news_hash(self, item: Dict[str, Any]) -> str:
        """Generate a unique hash for a news item based on title and link"""
        # Use title + link to create a unique identifier
        unique_string = f"{item.get('title', '')}|{item.get('link', '')}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def _extract_image_from_entry(self, entry) -> Optional[str]:
        """Extract image URL from RSS feed entry"""
        try:
            # Try to get image from media:content or media:thumbnail
            if hasattr(entry, 'media_content') and entry.media_content:
                return entry.media_content[0].get('url')
            
            if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
                return entry.media_thumbnail[0].get('url')
            
            # Try to get image from enclosures
            if hasattr(entry, 'enclosures') and entry.enclosures:
                for enclosure in entry.enclosures:
                    if enclosure.get('type', '').startswith('image/'):
                        return enclosure.get('href')
            
            # Try to extract from summary/description HTML
            if hasattr(entry, 'summary'):
                soup = BeautifulSoup(entry.summary, 'html.parser')
                img = soup.find('img')
                if img and img.get('src'):
                    return img.get('src')
            
            return None
        except Exception as e:
            return None
    
    def _fetch_image_from_article(self, url: str) -> Optional[str]:
        """Fetch image from article page (fallback method)"""
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (compatible; VCNewsBot/1.0)'}
            response = requests.get(url, headers=headers, timeout=5)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Try Open Graph image
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                return og_image.get('content')
            
            # Try Twitter card image
            twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
            if twitter_image and twitter_image.get('content'):
                return twitter_image.get('content')
            
            # Try first article image
            article = soup.find('article')
            if article:
                img = article.find('img')
                if img and img.get('src'):
                    img_url = img.get('src')
                    # Handle relative URLs
                    if img_url.startswith('//'):
                        return 'https:' + img_url
                    elif img_url.startswith('/'):
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        return f"{parsed.scheme}://{parsed.netloc}{img_url}"
                    return img_url
            
            return None
        except Exception as e:
            return None
    
    def _fetch_image_with_selenium(self, url: str) -> Optional[str]:
        """Fetch image from a page using Selenium to handle JavaScript rendering."""
        driver = None
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-software-rasterizer")
            chrome_options.add_argument("--single-process")  # Critical for Raspberry Pi
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")
            
            # Set page load timeout to prevent hanging
            chrome_options.page_load_strategy = 'eager'

            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(15)  # 15 second timeout
            driver.get(url)
            
            # Wait for the main image or article body to be present
            wait = WebDriverWait(driver, 10)
            
            try:
                # Look for Open Graph image first, as it's the most reliable
                og_image = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "meta[property='og:image']")))
                if og_image:
                    image_url = og_image.get_attribute('content')
                    return image_url
            except TimeoutException:
                logger.debug(f"No OG image found for {url}")
            
            try:
                # Fallback to the first image in the article tag
                article_image = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article img")))
                if article_image:
                    image_url = article_image.get_attribute('src')
                    return image_url
            except TimeoutException:
                logger.debug(f"No article image found for {url}")
            
            return None

        except (TimeoutException, WebDriverException) as e:
            logger.warning(f"Selenium scraping failed for {url}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in Selenium scraping for {url}: {str(e)}")
            return None
        finally:
            # CRITICAL: Always close the driver to prevent memory leaks
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    logger.error(f"Error closing Selenium driver: {str(e)}")

    def _normalize_url(self, url: str) -> str:
        """Normalize URL by removing query parameters and fragments"""
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        # Keep only scheme, netloc, and path (remove query, fragment)
        normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
        # Remove trailing slash for consistency
        return normalized.rstrip('/')
    
    def _generate_url_hash(self, item: Dict[str, Any]) -> str:
        """Generate a hash based only on the normalized URL"""
        url = item.get('link', '')
        if not url:
            return None
        normalized_url = self._normalize_url(url)
        return hashlib.md5(normalized_url.encode()).hexdigest()
    
    def _load_history(self) -> Dict[str, float]:
        """Load sent news history from JSON file"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    history = json.load(f)
                    # Clean up old entries (older than 7 days)
                    current_time = time.time()
                    cleaned_history = {
                        hash_id: timestamp 
                        for hash_id, timestamp in history.items()
                        if current_time - timestamp < 7 * 24 * 60 * 60  # 7 days
                    }
                    print(f"📚 Loaded {len(cleaned_history)} items from history (cleaned {len(history) - len(cleaned_history)} old entries)")
                    return cleaned_history
            except Exception as e:
                print(f"⚠ Error loading history: {str(e)}")
                return {}
        return {}
    
    def _save_history(self) -> None:
        """Save sent news history to JSON file"""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.sent_news_hashes, f, indent=2)
        except Exception as e:
            print(f"⚠ Error saving history: {str(e)}")
    
    def _is_duplicate(self, item: Dict[str, Any]) -> bool:
        """Check if a news item has already been analyzed (by title+link OR by URL)"""
        # Check title+link hash
        news_hash = self._generate_news_hash(item)
        if news_hash in self.sent_news_hashes:
            return True
        
        # Also check URL-only hash (catches same story from different sources)
        url_hash = self._generate_url_hash(item)
        if url_hash and url_hash in self.sent_news_hashes:
            return True
        
        return False
    
    def _mark_as_analyzed(self, item: Dict[str, Any]) -> None:
        """Mark a news item as analyzed (whether opportunity or not)"""
        # Store both title+link hash and URL-only hash
        news_hash = self._generate_news_hash(item)
        self.sent_news_hashes[news_hash] = time.time()
        
        # Also store URL hash to catch same story from different sources
        url_hash = self._generate_url_hash(item)
        if url_hash:
            self.sent_news_hashes[url_hash] = time.time()
        
    def _fetch_single_feed(self, source_name: str, feed_url: str) -> List[Dict[str, Any]]:
        """Fetch a single RSS feed with timeout protection"""
        articles = []
        
        try:
            # Always fetch with requests first to have better timeout control
            headers = {'User-Agent': 'Mozilla/5.0 (compatible; VCNewsBot/1.0)'}
            response = requests.get(feed_url, headers=headers, timeout=15, allow_redirects=True)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            
            # Debug: Check if feed has errors
            if hasattr(feed, 'bozo') and feed.bozo:
                logger.warning(f"Feed parsing warning for {source_name}: {feed.get('bozo_exception', 'Unknown error')}")
            
            # Debug: Check total entries available
            if len(feed.entries) == 0:
                logger.warning(f"No entries found in {source_name} feed. Status: {feed.get('status', 'N/A')}")
                return articles
            
            for entry in feed.entries[:10]:  # Limit to 10 most recent
                article = {
                    'source': source_name,
                    'title': entry.title,
                    'link': entry.link,
                    'summary': entry.get('summary', ''),
                    'image_url': self._extract_image_from_entry(entry),
                    'published': entry.get('published', ''),
                    'type': 'rss'
                }
                articles.append(article)
            
            logger.info(f"✓ Fetched {len(articles)} articles from {source_name}")
            
        except requests.Timeout:
            logger.error(f"Timeout fetching {source_name} (15s limit exceeded)")
        except Exception as e:
            logger.error(f"Error fetching {source_name}: {str(e)}")
        
        return articles
    
    def fetch_rss_feeds(self) -> List[Dict[str, Any]]:
        """Fetch articles from all RSS feeds"""
        all_articles = []
        
        for source_name, feed_url in self.rss_feeds.items():
            try:
                logger.info(f"Fetching RSS feed from {source_name}...")
                articles = self._fetch_single_feed(source_name, feed_url)
                all_articles.extend(articles)
            except Exception as e:
                logger.error(f"Unexpected error with {source_name}: {str(e)}", exc_info=True)
        
        return all_articles
    
    
    def merge_sources(self, *sources) -> List[Dict[str, Any]]:
        """Merge all data sources into a single list"""
        merged = []
        for source in sources:
            if isinstance(source, list):
                merged.extend(source)
        
        logger.info(f"Total items collected: {len(merged)}")
        return merged
    
    @retry_on_failure(max_retries=3, delay=10)
    def analyze_with_gemini(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analyze items using Google Gemini 2.5 Flash to identify opportunities"""
        if not self.gemini_api_key:
            logger.warning("Gemini API key not set, skipping AI analysis")
            return []
        
        # Select a random prompt style for this run
        if self.prompts:
            prompt_key = random.choice(list(self.prompts.keys()))
            prompt_data = self.prompts[prompt_key]
            prompt_template = prompt_data['prompt']
            prompt_emoji = prompt_data['emoji']
            self.current_prompt_style = prompt_key
            logger.info(f"Analyzing with '{prompt_key}' style {prompt_emoji}...")
        else:
            logger.info("Analyzing content with Google Gemini 2.5 Flash...")
            prompt_template = None
        
        analyzed_items = []
        
        # Batch items for analysis (process in groups)
        batch_size = 5
        for i in range(0, len(items), batch_size):
            batch = items[i:i+batch_size]
            
            # Prepare content for analysis
            content_summary = "\n\n".join([
                f"Source {idx+1} ({item['source']}):\n"
                f"Title: {item['title']}\n"
                f"Summary: {item.get('summary', '')[:500]}"
                for idx, item in enumerate(batch)
            ])
            
            # Use selected prompt template or default
            if prompt_template:
                prompt = prompt_template.format(content_summary=content_summary)
            else:
                # Fallback to original prompt
                prompt = f"""Analyze the following VC and startup news items and identify potential investment or business opportunities.

For each item, determine:
1. Is this a significant opportunity? (YES/NO)
2. What type of opportunity? (funding round, new startup launch, market trend, technology breakthrough, partnership, acquisition, IPO, etc.)
3. Risk level (LOW/MEDIUM/HIGH)
4. Brief explanation (max 2 sentences)

Content to analyze:
{content_summary}

Respond in JSON format for each item:
{{
    "item_1": {{
        "is_opportunity": true/false,
        "opportunity_type": "type",
        "risk_level": "LOW/MEDIUM/HIGH",
        "explanation": "brief explanation"
    }},
    ...
}}"""
            
            try:
                response = self.model.generate_content(prompt)
                
                # Parse the response
                response_text = response.text.strip()
                
                # Try to extract JSON from the response
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()
                
                try:
                    analysis = json.loads(response_text)
                    
                    # Match analysis results with items
                    for idx, item in enumerate(batch):
                        item_key = f"item_{idx+1}"
                        if item_key in analysis:
                            item_analysis = analysis[item_key]
                            item['ai_analysis'] = item_analysis
                            item['is_opportunity'] = item_analysis.get('is_opportunity', False)
                            analyzed_items.append(item)
                        else:
                            item['ai_analysis'] = None
                            item['is_opportunity'] = False
                            analyzed_items.append(item)
                    
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse JSON response for batch {i//batch_size + 1}")
                    # Add items without analysis
                    for item in batch:
                        item['ai_analysis'] = {'explanation': response_text[:200]}
                        item['is_opportunity'] = False
                        analyzed_items.append(item)
                
                # Rate limiting - be nice to the API
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Error analyzing batch {i//batch_size + 1}: {str(e)}", exc_info=True)
                # Add items without analysis
                for item in batch:
                    item['ai_analysis'] = None
                    item['is_opportunity'] = False
                    analyzed_items.append(item)
        
        return analyzed_items
    
    def filter_opportunities(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter items to only include identified opportunities"""
        opportunities = [item for item in items if item.get('is_opportunity', False)]
        
        logger.info(f"Found {len(opportunities)} opportunities out of {len(items)} items")
        return opportunities
    
    def filter_duplicates(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out previously analyzed items (opportunities AND non-opportunities)"""
        new_items = []
        duplicate_count = 0
        
        for item in items:
            if not self._is_duplicate(item):
                new_items.append(item)
            else:
                duplicate_count += 1
        
        logger.info(f"Filtered out {duplicate_count} already-analyzed item(s), {len(new_items)} new items to analyze")
        return new_items
    
    def send_to_telegram(self, opportunities: List[Dict[str, Any]]) -> None:
        """Send opportunities to Telegram"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("⚠ Telegram credentials not set, skipping notification")
            print("\n📋 Opportunities found:")
            for idx, opp in enumerate(opportunities, 1):
                print(f"\n{idx}. {opp['title']}")
                print(f"   Source: {opp['source']}")
                if opp.get('ai_analysis'):
                    print(f"   Analysis: {opp['ai_analysis'].get('explanation', 'N/A')}")
                    print(f"   Risk: {opp['ai_analysis'].get('risk_level', 'N/A')}")
            return
        
        if not opportunities:
            print("ℹ No opportunities to send")
            return
        
        print(f"\n📱 Sending {len(opportunities)} opportunities to Telegram...")
        
        telegram_api = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        
        for opp in opportunities:
            try:
                # Format message using template
                analysis = opp.get('ai_analysis', {})
                
                # Get prompt emoji and template
                style = self.current_prompt_style or 'original'
                prompt_emoji = '🚀'
                template = None
                
                if self.prompts and style in self.prompts:
                    prompt_emoji = self.prompts[style].get('emoji', '🚀')
                
                if self.message_templates and style in self.message_templates:
                    template = self.message_templates[style].get('template')
                
                # Format message with template or use default
                if template:
                    try:
                        message = template.format(
                            emoji=prompt_emoji,
                            source=opp['source'],
                            title=opp['title'],
                            opportunity_type=analysis.get('opportunity_type', 'N/A'),
                            risk_level=analysis.get('risk_level', 'N/A'),
                            explanation=analysis.get('explanation', 'No analysis available'),
                            link=opp.get('link', 'N/A'),
                            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            style=style
                        )
                    except Exception as template_error:
                        print(f"⚠ Template formatting failed: {str(template_error)}, using default...")
                        template = None
                else:
                    # Fallback to default format
                    message = f"""
{prompt_emoji} *VC/Startup Opportunity Detected*

*Source:* {opp['source']}
*Title:* {opp['title']}

*Type:* {analysis.get('opportunity_type', 'N/A')}
*Risk Level:* {analysis.get('risk_level', 'N/A')}

*Analysis:*
{analysis.get('explanation', 'No analysis available')}

*Link:* {opp.get('link', 'N/A')}

_Analyzed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_
_Style: {style}_
"""
                
                # Try to get image URL
                image_url = opp.get('image_url')
                
                # If no image in RSS, try fetching from the article URL
                if not image_url:
                    article_url = opp.get('link', '')
                    if article_url:
                        # First, try the fast, simple scraper
                        print(f"ℹ No RSS image for '{opp['title'][:30]}...'. Trying simple scrape.")
                        image_url = self._fetch_image_from_article(article_url)
                        
                        # If the simple scraper fails, use the powerful (but slower) Selenium scraper
                        if not image_url:
                            print(f"ℹ Simple scrape failed. Trying advanced scrape with Selenium...")
                            image_url = self._fetch_image_with_selenium(article_url)
                
                # Send with image if available, otherwise text only
                sent_successfully = False
                if image_url:
                    # Check if message exceeds Telegram's caption limit (1024 chars)
                    if len(message) > 1024:
                        print("ℹ Message is too long for a caption. Sending image and text separately.")
                        try:
                            # Send the photo without a caption
                            photo_api = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendPhoto"
                            photo_payload = {'chat_id': self.telegram_chat_id, 'photo': image_url}
                            photo_response = requests.post(photo_api, json=photo_payload, timeout=10)
                            photo_response.raise_for_status()
                            # The text will be sent in the 'if not sent_successfully' block below
                        except Exception as img_error:
                            print(f"⚠ Image failed to send separately ({str(img_error)}). Proceeding with text only.")
                    else:
                        # Message is short enough for a caption
                        try:
                            photo_api = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendPhoto"
                            payload = {
                                'chat_id': self.telegram_chat_id,
                                'photo': image_url,
                                'caption': message,
                                'parse_mode': 'Markdown'
                            }
                            response = requests.post(photo_api, json=payload, timeout=10)
                            response.raise_for_status()
                            sent_successfully = True
                        except Exception as img_error:
                            print(f"⚠ Image with caption failed ({str(img_error)}), sending as text...")
                
                # If no image or image failed, send as text
                if not sent_successfully:
                    # Try with Markdown first, fallback to plain text if it fails
                    payload = {
                        'chat_id': self.telegram_chat_id,
                        'text': message,
                        'parse_mode': 'Markdown',
                        'disable_web_page_preview': True
                    }
                    try:
                        response = requests.post(telegram_api, json=payload, timeout=10)
                        response.raise_for_status()
                    except Exception as markdown_error:
                        # If Markdown fails, try without parse_mode (plain text)
                        print(f"⚠ Markdown failed, sending as plain text...")
                        payload = {
                            'chat_id': self.telegram_chat_id,
                            'text': message.replace('*', '').replace('_', ''),  # Remove markdown formatting
                            'disable_web_page_preview': True
                        }
                        response = requests.post(telegram_api, json=payload, timeout=10)
                        response.raise_for_status()
                
                print(f"✓ Sent: {opp['title'][:50]}...")
                time.sleep(1)  # Rate limiting
                
            except Exception as e:
                print(f"✗ Error sending to Telegram: {str(e)}")
    
    def run_workflow(self) -> None:
        """Execute the complete workflow"""
        # Check for quiet hours (10 PM to 7 AM)
        current_hour = datetime.now().hour
        if current_hour >= 22 or current_hour < 7:
            logger.info("Quiet hours are active (10 PM - 7 AM). Skipping run.")
            return
            
        logger.info("="*60)
        logger.info("Starting VC & Startup News Analysis Workflow")
        logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*60)
        
        try:
            # Step 1: Fetch all sources
            rss_articles = self.fetch_rss_feeds()
            
            # Step 2: Merge sources
            all_items = self.merge_sources(rss_articles)
            
            if not all_items:
                logger.warning("No items collected. Exiting workflow.")
                return
            
            # Step 3: Filter out already-posted items (only items sent to Telegram are marked as duplicates)
            new_items = self.filter_duplicates(all_items)
            
            if not new_items:
                logger.info("No new items to analyze. All items were duplicates.")
                return
            
            # Step 4: AI Analysis (only on new items)
            analyzed_items = self.analyze_with_gemini(new_items)
            
            # Step 5: Filter opportunities
            opportunities = self.filter_opportunities(analyzed_items)
            
            # Step 6: Randomly select 1-3 opportunities to send
            if opportunities:
                max_posts = random.randint(1, 3)
                selected_opportunities = random.sample(opportunities, min(max_posts, len(opportunities)))
                logger.info(f"Randomly selected {len(selected_opportunities)} out of {len(opportunities)} opportunities to post")
            else:
                selected_opportunities = []
            
            # Step 7: Send to Telegram
            self.send_to_telegram(selected_opportunities)
            
            # Step 8: Mark ONLY posted items as analyzed (to avoid re-posting)
            for item in selected_opportunities:
                self._mark_as_analyzed(item)
            
            # Step 9: Save history
            self._save_history()
            
            logger.info("="*60)
            logger.info("Workflow completed successfully!")
            logger.info("="*60)
            
        except Exception as e:
            logger.error(f"Workflow error: {str(e)}", exc_info=True)
            # Don't re-raise - let the bot continue running


def main():
    """Main function to run the analyzer"""
    logger.info("="*60)
    logger.info("VC & Startup News Analyzer Bot Starting")
    logger.info("="*60)
    
    try:
        analyzer = VCNewsAnalyzer()
        
        # Run immediately
        logger.info("Running initial workflow...")
        try:
            analyzer.run_workflow()
        except Exception as e:
            logger.error(f"Initial workflow failed: {str(e)}", exc_info=True)
        
        # Schedule to run every hour (adjust as needed)
        schedule.every(1).hours.do(analyzer.run_workflow)
        
        logger.info("Scheduler started. Running every 1 hour.")
        logger.info("Press Ctrl+C to stop.")
        
        # Keep the script running with error recovery
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while True:
            try:
                schedule.run_pending()
                consecutive_errors = 0  # Reset on success
                time.sleep(60)
            except KeyboardInterrupt:
                logger.info("Received shutdown signal. Exiting gracefully...")
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error in main loop (consecutive errors: {consecutive_errors}): {str(e)}", exc_info=True)
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(f"Too many consecutive errors ({max_consecutive_errors}). Shutting down.")
                    sys.exit(1)
                
                # Wait before retrying
                time.sleep(60)
    
    except Exception as e:
        logger.critical(f"Fatal error in main: {str(e)}", exc_info=True)
        sys.exit(1)
    
    logger.info("Bot shutdown complete.")


if __name__ == "__main__":
    main()
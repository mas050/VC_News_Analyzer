# VC & Startup News Analyzer

An automated bot that monitors VC and startup news from multiple RSS feeds, analyzes them using Google Gemini AI, and posts opportunities to Telegram.

## 🚀 Features

- **10 Premium RSS Feeds**: Tracks news from Crunchbase, TechCrunch, VentureBeat, and top VC blogs
- **AI-Powered Analysis**: Uses Google Gemini 2.5 Flash to identify investment opportunities
- **12 Analysis Styles**: Varied perspectives (funding focus, unicorn watch, market disruption, etc.)
- **Smart Filtering**: Only posts articles once, but re-analyzes with different perspectives
- **Automated Posting**: Posts 1-3 opportunities per hour to your Telegram channel
- **Image Support**: Automatically fetches and includes article images
- **Quiet Hours**: Respects sleep time (10 PM - 7 AM)

## 📋 Prerequisites

- Python 3.8+
- Raspberry Pi (or any Linux system)
- Google Gemini API Key
- Telegram Bot Token
- Telegram Chat/Channel ID

## 🔧 Installation

### 1. Clone the Repository

```bash
cd ~
git clone https://github.com/mas050/VC_News_Analyzer.git
cd VC_News_Analyzer
```

### 2. Install System Dependencies

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Python and pip
sudo apt-get install python3 python3-pip python3-venv -y

# Install Chrome and ChromeDriver (for image scraping)
sudo apt-get install chromium-chromedriver -y
```

### 3. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Python Dependencies

```bash
pip install --upgrade pip
pip install feedparser requests schedule python-dotenv google-generativeai beautifulsoup4 selenium
```

### 5. Configure Environment Variables

```bash
cp .env.example .env
nano .env
```

Add your credentials:
```
GEMINI_API_KEY=your_gemini_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
```

Save and exit (Ctrl+X, Y, Enter)

## 🎯 Getting API Keys

### Google Gemini API Key
1. Visit https://makersuite.google.com/app/apikey
2. Click "Create API Key"
3. Copy the key to your `.env` file

### Telegram Bot Token
1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow instructions
3. Copy the token to your `.env` file

### Telegram Chat ID
1. Add your bot to your channel as administrator
2. Send a message to the channel
3. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Find the `chat` object and copy the `id` (negative number for channels)

## 🏃 Running the Bot

### Manual Run (for testing)

```bash
cd ~/VC_News_Analyzer
source venv/bin/activate
python3 VC_News_Analyzer.py
```

Press `Ctrl+C` to stop.

### Run as Background Service (Recommended)

See [RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md) for systemd service configuration.

## 📁 Project Structure

```
VC_News_Analyzer/
├── VC_News_Analyzer.py      # Main bot script
├── prompts.json              # AI analysis prompt variations
├── message_templates.json    # Telegram message templates
├── .env                      # Environment variables (not in git)
├── sent_news_history.json    # Tracks posted articles (auto-generated)
├── vc_news_bot.log          # Application logs (auto-generated)
├── README.md                 # This file
├── RASPBERRY_PI_SETUP.md    # Raspberry Pi setup guide
├── requirements.txt          # Python dependencies
└── .gitignore               # Git ignore rules
```

## 🔄 Updating the Bot

```bash
cd ~/VC_News_Analyzer
git pull origin main
source venv/bin/activate
pip install -r requirements.txt --upgrade
sudo systemctl restart vc-news-bot
```

## 📊 Monitoring

### View Logs
```bash
# Real-time logs
tail -f ~/VC_News_Analyzer/vc_news_bot.log

# Last 100 lines
tail -n 100 ~/VC_News_Analyzer/vc_news_bot.log

# Search for errors
grep -i error ~/VC_News_Analyzer/vc_news_bot.log
```

### Check Service Status
```bash
sudo systemctl status vc-news-bot
```

### View Posted Articles History
```bash
cat ~/VC_News_Analyzer/sent_news_history.json | python3 -m json.tool
```

## 🛠️ Troubleshooting

### Bot Not Posting
1. Check logs: `tail -f ~/VC_News_Analyzer/vc_news_bot.log`
2. Verify API keys in `.env`
3. Test Telegram connection: Send a test message manually
4. Check if it's quiet hours (10 PM - 7 AM)

### Selenium/Chrome Issues
```bash
# Reinstall ChromeDriver
sudo apt-get install --reinstall chromium-chromedriver -y
```

### Memory Issues on Raspberry Pi
```bash
# Increase swap space
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Change CONF_SWAPSIZE=100 to CONF_SWAPSIZE=1024
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

## 🎨 Customization

### Change Posting Frequency
Edit line 796 in `VC_News_Analyzer.py`:
```python
schedule.every(1).hours.do(analyzer.run_workflow)  # Change 1 to desired hours
```

### Adjust Posts Per Hour
Edit line 753 in `VC_News_Analyzer.py`:
```python
max_posts = random.randint(1, 3)  # Change range (min, max)
```

### Modify Quiet Hours
Edit lines 718-721 in `VC_News_Analyzer.py`:
```python
if current_hour >= 22 or current_hour < 7:  # 10 PM to 7 AM
```

### Add More RSS Feeds

Edit the `self.rss_feeds` dictionary in `VC_News_Analyzer.py` (lines 107-118):

```python
self.rss_feeds = {
    'Crunchbase News': 'https://news.crunchbase.com/feed/',
    'Above the Crowd': 'https://abovethecrowd.com/feed/',
    # ... existing feeds ...
    'Your New Feed Name': 'https://example.com/feed/',  # Add new feeds here
}
```

**Format:**
- `'Display Name': 'RSS Feed URL',`
- Display Name: How it appears in Telegram posts
- RSS Feed URL: The actual feed URL (usually ends in `/feed/`, `/rss/`, or `.xml`)
- Don't forget the comma at the end (except for the last entry)

**Finding RSS Feeds:**
Most sites have RSS at `/feed/`, `/rss/`, `/feed.xml`, or look for the RSS icon 📡

**After adding:**
1. Save and commit: `git add VC_News_Analyzer.py && git commit -m "Add new RSS feed"`
2. Push to GitHub: `git push origin main`
3. Update on Raspberry Pi:
   ```bash
   cd ~/Python/VC_News_Analyzer
   sudo systemctl stop vc-news-bot
   git pull origin main
   sudo systemctl start vc-news-bot
   ```

## 📝 License

MIT License - Feel free to use and modify.

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first.

## 📧 Support

For issues and questions, please open a GitHub issue.

---

**Made with ❤️ for the VC and startup community**

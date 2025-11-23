# Raspberry Pi Setup Guide

Complete guide to set up the VC News Analyzer as an auto-starting service on Raspberry Pi.

## 📦 Initial Setup

### 1. Fresh Raspberry Pi Setup

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get dist-upgrade -y

# Install essential tools
sudo apt-get install git python3 python3-pip python3-venv chromium-chromedriver -y

# Reboot to apply updates
sudo reboot
```

### 2. Clone Repository

```bash
cd ~
git clone https://github.com/mas050/VC_News_Analyzer.git
cd VC_News_Analyzer
```

### 3. Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install feedparser requests schedule python-dotenv google-generativeai beautifulsoup4 selenium
```

### 4. Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit with your credentials
nano .env
```

Add your API keys:
```
GEMINI_API_KEY=your_actual_key_here
TELEGRAM_BOT_TOKEN=your_actual_token_here
TELEGRAM_CHAT_ID=your_actual_chat_id_here
```

Save: `Ctrl+X`, then `Y`, then `Enter`

### 5. Test Run

```bash
# Make sure you're in the virtual environment
source ~/VC_News_Analyzer/venv/bin/activate

# Run the bot
python3 VC_News_Analyzer.py
```

Watch for any errors. Press `Ctrl+C` to stop after confirming it works.

## 🔄 Set Up as Systemd Service

### 1. Create Service File

```bash
sudo nano /etc/systemd/system/vc-news-bot.service
```

### 2. Add Service Configuration

```ini
[Unit]
Description=VC & Startup News Analyzer Bot
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/VC_News_Analyzer
Environment="PATH=/home/pi/VC_News_Analyzer/venv/bin"
ExecStart=/home/pi/VC_News_Analyzer/venv/bin/python3 /home/pi/VC_News_Analyzer/VC_News_Analyzer.py
Restart=always
RestartSec=60
StandardOutput=append:/home/pi/VC_News_Analyzer/vc_news_bot.log
StandardError=append:/home/pi/VC_News_Analyzer/vc_news_bot.log

[Install]
WantedBy=multi-user.target
```

**Note**: If your username is not `pi`, replace all instances of `pi` with your actual username.

Save: `Ctrl+X`, then `Y`, then `Enter`

### 3. Enable and Start Service

```bash
# Reload systemd to recognize new service
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable vc-news-bot

# Start the service now
sudo systemctl start vc-news-bot

# Check status
sudo systemctl status vc-news-bot
```

You should see "active (running)" in green.

## 🎮 Service Management Commands

### Check Service Status
```bash
sudo systemctl status vc-news-bot
```

### Start Service
```bash
sudo systemctl start vc-news-bot
```

### Stop Service
```bash
sudo systemctl stop vc-news-bot
```

### Restart Service
```bash
sudo systemctl restart vc-news-bot
```

### View Real-Time Logs
```bash
# Follow logs as they're written
tail -f ~/VC_News_Analyzer/vc_news_bot.log

# Or use journalctl
sudo journalctl -u vc-news-bot -f
```

### View Last 100 Log Lines
```bash
tail -n 100 ~/VC_News_Analyzer/vc_news_bot.log
```

### Search Logs for Errors
```bash
grep -i error ~/VC_News_Analyzer/vc_news_bot.log
```

### Disable Auto-Start on Boot
```bash
sudo systemctl disable vc-news-bot
```

### Re-Enable Auto-Start on Boot
```bash
sudo systemctl enable vc-news-bot
```

## 🔄 Updating the Bot

When you push updates to GitHub, follow these steps on your Raspberry Pi:

### 1. Stop the Service
```bash
sudo systemctl stop vc-news-bot
```

### 2. Pull Latest Changes
```bash
cd ~/VC_News_Analyzer
git pull origin main
```

### 3. Update Dependencies (if needed)
```bash
source venv/bin/activate
pip install -r requirements.txt --upgrade
```

### 4. Restart the Service
```bash
sudo systemctl start vc-news-bot
```

### 5. Verify It's Running
```bash
sudo systemctl status vc-news-bot
tail -f ~/VC_News_Analyzer/vc_news_bot.log
```

## 🔧 Quick Update Script

Create a convenience script for updates:

```bash
nano ~/update-vc-bot.sh
```

Add this content:
```bash
#!/bin/bash
echo "Stopping VC News Bot..."
sudo systemctl stop vc-news-bot

echo "Pulling latest changes..."
cd ~/VC_News_Analyzer
git pull origin main

echo "Updating dependencies..."
source venv/bin/activate
pip install -r requirements.txt --upgrade

echo "Starting VC News Bot..."
sudo systemctl start vc-news-bot

echo "Checking status..."
sleep 2
sudo systemctl status vc-news-bot

echo "Done! Tailing logs (Ctrl+C to exit)..."
tail -f ~/VC_News_Analyzer/vc_news_bot.log
```

Make it executable:
```bash
chmod +x ~/update-vc-bot.sh
```

Now you can update with:
```bash
~/update-vc-bot.sh
```

## 📊 Monitoring & Maintenance

### Check Disk Space
```bash
df -h
```

### Check Memory Usage
```bash
free -h
```

### Check Bot Process
```bash
ps aux | grep VC_News_Analyzer
```

### Rotate Logs (if they get too large)
```bash
# Archive old logs
cd ~/VC_News_Analyzer
mv vc_news_bot.log vc_news_bot.log.old
sudo systemctl restart vc-news-bot
```

### Clean Up Old History (optional)
The bot auto-cleans history older than 7 days, but you can manually reset:
```bash
cd ~/VC_News_Analyzer
# Backup first
cp sent_news_history.json sent_news_history.json.backup
# Clear history
echo "{}" > sent_news_history.json
sudo systemctl restart vc-news-bot
```

## 🚨 Troubleshooting

### Service Won't Start
```bash
# Check for syntax errors
sudo systemctl status vc-news-bot

# Check detailed logs
sudo journalctl -u vc-news-bot -n 50 --no-pager

# Verify Python path
which python3
ls -la ~/VC_News_Analyzer/venv/bin/python3
```

### Bot Crashes After Running
```bash
# Check logs for errors
tail -n 100 ~/VC_News_Analyzer/vc_news_bot.log

# Check system resources
top
free -h

# Increase swap if needed (see README.md)
```

### Git Pull Conflicts
```bash
cd ~/VC_News_Analyzer
# Stash local changes
git stash
# Pull updates
git pull origin main
# Reapply your changes if needed
git stash pop
```

### Permissions Issues
```bash
# Fix ownership
sudo chown -R pi:pi ~/VC_News_Analyzer

# Fix permissions
chmod +x ~/VC_News_Analyzer/VC_News_Analyzer.py
```

## 🔐 Security Best Practices

1. **Never commit `.env` file** - It contains your API keys
2. **Keep system updated**: Run `sudo apt-get update && sudo apt-get upgrade` monthly
3. **Use strong passwords** for your Raspberry Pi
4. **Limit SSH access** if exposed to internet
5. **Backup your `.env` file** securely

## 📱 Remote Access

### SSH into Raspberry Pi
```bash
ssh pi@your-raspberry-pi-ip
```

### Run Commands Remotely
```bash
# Check status
ssh pi@your-pi-ip "sudo systemctl status vc-news-bot"

# View logs
ssh pi@your-pi-ip "tail -n 50 ~/VC_News_Analyzer/vc_news_bot.log"
```

## 🎯 Performance Optimization

### For Raspberry Pi Zero/1
```bash
# Reduce batch size in VC_News_Analyzer.py line 455
batch_size = 3  # Instead of 5

# Increase restart delay in service file
RestartSec=120  # Instead of 60
```

### For Raspberry Pi 4+
```bash
# Can handle default settings
# Consider running multiple instances for different topics
```

## ✅ Verification Checklist

After setup, verify:
- [ ] Service starts automatically after reboot: `sudo reboot` then check `sudo systemctl status vc-news-bot`
- [ ] Logs are being written: `tail -f ~/VC_News_Analyzer/vc_news_bot.log`
- [ ] Posts appear in Telegram channel
- [ ] History file is updating: `ls -lh ~/VC_News_Analyzer/sent_news_history.json`
- [ ] No errors in logs: `grep -i error ~/VC_News_Analyzer/vc_news_bot.log`

---

**Your VC News Analyzer is now running 24/7! 🚀**

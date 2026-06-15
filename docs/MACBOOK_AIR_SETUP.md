# MacBook Air (M-Series) Setup Guide - Elite Run V4

This guide helps you set up and run the specialized **Elite Run V4** discovery pipeline on your MacBook Air. Since this is an M-series (ARM) machine, we ensure all dependencies are compatible.

## 1. Prerequisites (Homebrew & Python)
Open your terminal and ensure you have the basics:
```bash
# Install Homebrew if not already present
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.11+
brew install python@3.11
```

## 2. Project Setup
Clone the repository and move into the project folder:
```bash
git clone git@github.com:slingvector/instagram-ai-automation.git
cd instagram-ai-automation
git checkout cloud-ready # Or the branch where we pushed V4
```

## 3. Virtual Environment & Dependencies
```bash
# Create and activate venv
python3 -m venv venv
source venv/bin/activate

# Install core dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install Playwright browsers (Crucial for scraping)
playwright install chromium
```

## 4. Credentials & Config
Make sure these files are present in the root directory:
- `token.json` (Google Drive OAuth token)
- `credentials.json` (Google Cloud Desktop app credentials)
- `.env` (With any relevant environment variables)

Check the isolated V4 config files:
- `config/elite_v4_discovery.yaml` (Engagement filters/Seeds)
- `config/elite_v4_manifest.yaml` (Current progress - copies of yours from the other machine)

## 5. Running the Pipeline
To run the full 10k accounts discovery in the background:
```bash
TARGET_ACCOUNTS=10000 TARGET_REELS=500 nohup python3 scripts/elite_v4_pipeline.py > logs/elite_v4_out.log 2>&1 & echo $! > data/elite_v4_pid.txt
```

## 6. Monitoring on MacBook Air
- **Check Status**: `tail -f logs/elite_v4.log`
- **Verify Background Process**: `ps -p $(cat data/elite_v4_pid.txt)`
- **Isolated Data**: All discoveries go to `data/elite_v4_dedup.db`.

---
**Note for MBA**: The MacBook Air is fanless. Running 1000s of headless Chrome pages will heat it up. If you notice significant slowdown, consider reducing the concurrency or spreading the run over more sessions.

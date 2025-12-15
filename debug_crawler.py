import sys
import os
import logging
import io
from datetime import datetime, timezone

# Add path
sys.path.append(os.getcwd())

# Capture logs to string buffer
log_capture_string = io.StringIO()
ch = logging.StreamHandler(log_capture_string)
ch.setLevel(logging.INFO)
# Remove other handlers
root = logging.getLogger()
root.handlers = []

# Config logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", handlers=[ch])

from app.core import config
config.logger = logging.getLogger("DebugLogger")
config.logger.handlers = [ch] # Ensure config logger also uses this handler
config.logger.setLevel(logging.INFO)

from app.services import news_crawler

def test_crawler():
    output = []
    output.append("Testing News Crawler...")
    output.append(f"Sources: {[s['name'] for s in config.NEWS_SOURCES]}")
    
    try:
        # Run with large lookback
        articles = news_crawler.get_gold_news(lookback_minutes=48*60)
        
        output.append(f"Total NEW articles added: {len(articles)}")
        for art in articles:
            output.append(f"- [{art['source']}] {art['title']}")
    except Exception as e:
        output.append(f"CRASH: {e}")
        import traceback
        output.append(traceback.format_exc())

    # Get logs
    log_contents = log_capture_string.getvalue()
    
    with open("crawler_results.txt", "w", encoding="utf-8") as f:
        f.write("=== LOGS ===\n")
        f.write(log_contents)
        f.write("\n=== OUTPUT ===\n")
        f.write("\n".join(output))
    
    print("Done checking.")

if __name__ == "__main__":
    test_crawler()

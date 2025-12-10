# test_flow.py
import logging
import config
from database import init_db, check_keywords
from ai_engine import analyze_market
from charter import calculate_fibonacci_levels
import pandas as pd

# Setup fake logger for testing
logger = config.logger

def test_imports():
    logger.info("TEST 1: Kiểm tra Import...")
    try:
        import run_analysis
        logger.info("✅ Import run_analysis thành công.")
    except ImportError as e:
        logger.error(f"❌ Lỗi Import: {e}")

def test_database_init():
    logger.info("TEST 2: Kiểm tra Database Init...")
    try:
        init_db()
        logger.info("✅ Database Init thành công (không crash).")
    except Exception as e:
        logger.error(f"❌ Lỗi Database: {e}")

def test_keyword_logic():
    logger.info("TEST 3: Kiểm tra Keyword Logic...")
    text = "Gold price is rising due to Fed interest rate hike."
    kws = check_keywords(text)
    if "Gold" in kws and "Fed" in kws:
        logger.info(f"✅ Keyword Check thành công: {kws}")
    else:
        logger.error(f"❌ Keyword Check thất bại. Got: {kws}")

def test_fibo_calculation():
    logger.info("TEST 4: Kiểm tra tính Fibo...")
    data = {
        'High': [2000, 2010, 2005, 1990, 2020],
        'Low': [1980, 1990, 1985, 1970, 1995]
    }
    df = pd.DataFrame(data)
    levels, trend = calculate_fibonacci_levels(df)
    if levels and trend in ["UPTREND", "DOWNTREND", "SIDEWAY"]:
         logger.info(f"✅ Fibo Calc thành công. Trend: {trend}")
    else:
         logger.error("❌ Fibo Calc thất bại.")

def main():
    logger.info("=== BẮT ĐẦU TEST SCRIPT ===")
    test_imports()
    test_database_init()
    test_keyword_logic()
    test_fibo_calculation()
    logger.info("=== KẾT THÚC TEST SCRIPT ===")

if __name__ == "__main__":
    main()

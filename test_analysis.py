#!/usr/bin/env python
# Test script for get_technical_analysis

from app.services.charter import get_technical_analysis, get_market_data

if __name__ == "__main__":
    print("Testing Unified Data Flow...\n")
    
    # 1. Get Data
    print("1. Fetching Market Data...")
    df = get_market_data("XAUUSD")
    
    if df is not None:
        print(f"   Success! Shape: {df.shape}")
        
        # 2. Get Analysis
        print("\n2. Getting Technical Analysis...")
        result = get_technical_analysis(df)
        print("-" * 30)
        print(result)
        print("-" * 30)
    else:
        print("   Failed to fetch data!")

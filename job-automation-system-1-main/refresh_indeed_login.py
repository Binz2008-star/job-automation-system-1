#!/usr/bin/env python3
"""Manual login refresh for Indeed in Playwright profile"""

from playwright.sync_api import sync_playwright
import time

def main():
    print("Opening browser for Indeed login refresh...")
    print("Please log in to Indeed/Google in the browser window.")
    print("The browser will stay open for 60 seconds for you to complete login.")
    print("Close the browser window manually when done, or wait for timeout.")

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context('data/ng_profile', headless=False)
        page = ctx.new_page()
        page.goto('https://ae.indeed.com')

        # Wait for manual login or timeout
        for i in range(60):
            if page.is_closed():
                break
            time.sleep(1)
            if i % 10 == 0:
                print(f"Waiting... {60-i}s remaining")

        try:
            ctx.close()
            print("Login session saved. Browser closed.")
        except:
            print("Browser was closed manually.")

if __name__ == "__main__":
    main()

import re
from playwright.sync_api import Playwright

def run(playwright: Playwright, username: str = "***REMOVED***") -> None:
    
    #open browser
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://anonyig.com/en/")
    # Search for a user
    page.get_by_role("textbox", name="@username or link").click()
    page.get_by_role("textbox", name="@username or link").fill(username)
    # Click the search button
    page.get_by_role("button").filter(has_text=re.compile(r"^$")).click()
    # Wait for the page to load
    page.wait_for_timeout(2000)  # Adjust timeout as needed
    # Click on the "Stories" button
    page.get_by_role("button", name="stories").click()
    
    page.wait_for_timeout(2000)  # Adjust timeout as needed
    # Click on the "Stories" button
    page.get_by_role("button", name="stories").click()
    
    #lazy loading
    button = page.get_by_role("button", name="Features and How to Download")

    # Scroll and wait for content to load
    button.scroll_into_view_if_needed()
    print("Scrolled into view")
    
    # Wait for stories to load
    page.wait_for_timeout(5000)  # 5 seconds
    print("Content loading wait completed")

    # Middle-click approach (opens in new tabs)
    for i in range(3):
        try:
            button = page.locator(f"li:nth-child({i+1}) > .media-content__info > .button")
            
            # Middle-click to open in new tab
            with context.expect_page() as new_page_info:
                button.click(button="middle")
            
            # Get the new page
            new_page = new_page_info.value
            
            # Wait for the page to load
            new_page.wait_for_load_state('networkidle')
            
            # Look for download link
            download_link = new_page.locator("a[href*='download'], .download-btn, [download]").first
            
            if download_link.is_visible():
                with new_page.expect_download() as download_info:
                    download_link.click()
                download = download_info.value
                print(f"Downloaded story {i+1}: {download.suggested_filename}")
            
            # Close the new tab
            new_page.close()
            
        except Exception as e:
            print(f"Error with story {i+1}: {e}")
            continue
    
    page.get_by_role("listitem").filter(has_text="Download 23 hours ago").get_by_role("link").click()
    page.locator("[id=\"google_ads_iframe_/22720552842,22744570741/anonyig/fullscreen_0\"]").content_frame.locator("iframe[name=\"ad_iframe\"]").content_frame.get_by_role("button", name="Close ad").click()
    with page.expect_download() as download_info:
        page.get_by_role("link", name="Download", exact=True).click()
    download = download_info.value

    # ---------------------
    context.close()
    browser.close()


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright
    
    # Test with the profiles you mentioned
    test_usernames = ["***REMOVED***", "***REMOVED***"]
    
    for username in test_usernames:
        print(f"Testing download for: {username}")
        try:
            with sync_playwright() as playwright:
                run(playwright, username)
            print(f"Completed test for: {username}")
        except Exception as e:
            print(f"Error testing {username}: {e}")
        print("-" * 50)
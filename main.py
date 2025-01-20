import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Initialize the WebDriver
options = Options()
# Run in headless mode if you don't want the browser to appear
options.add_argument("--headless")
driver = webdriver.Chrome(service=Service(
    ChromeDriverManager().install()), options=options)

# Function to extract email addresses using regex


def extract_emails(text):
    email_regex = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return re.findall(email_regex, text)


# URL to scrape
url = "https://www.yellowpages.com/search?search_terms=software+company&geo_location_terms=San+Francisco%2C+CA"
driver.get(url)

# Allow the page to load
time.sleep(5)

# Collect company names and links to their individual pages
company_details = []
try:
    listings = driver.find_elements(
        By.CSS_SELECTOR, 'div.info')  # Adjust selector if needed
    for listing in listings:
        try:
            company_name = listing.find_element(
                By.CSS_SELECTOR, 'a.business-name').text
            company_link = listing.find_element(
                By.CSS_SELECTOR, 'a.business-name').get_attribute("href")
            company_details.append(
                {"name": company_name, "link": company_link})
        except Exception as e:
            print(f"Error extracting company details: {e}")
except Exception as e:
    print(f"Error while fetching company listings: {e}")

print(f"Found {len(company_details)} companies.")

# Visit each company page and extract emails
results = []
for company in company_details:
    try:
        driver.get(company["link"])
        time.sleep(3)  # Allow the page to load
        page_text = driver.page_source
        found_emails = extract_emails(page_text)
        if found_emails:
            results.append({"name": company["name"], "emails": found_emails})
    except Exception as e:
        print(
            f"Error while processing {company['name']} ({company['link']}): {e}")

# Output the collected company names and emails
print("Extracted Company Details:")
for result in results:
    print(f"Company Name: {result['name']}")
    for email in result['emails']:
        print(f"  Email: {email}")

# Close the WebDriver
driver.quit()

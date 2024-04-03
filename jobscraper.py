from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import pandas as pd
import re
from tqdm import tqdm
import time
import os
import hashlib
import pickle
from datetime import datetime
import sys
import traceback
from collections import Counter
import re
from datetime import timedelta
import argparse
from gpt_filter import filter_job_titles_by_interest
import json
import webbrowser


def initialize_driver():
    options = Options()
    options.add_argument("--window-size=1920,1080");
    options.add_argument("--disable-gpu");
    options.add_argument("--disable-extensions");
    options.add_argument("--start-maximized");
    options.add_argument("--headless");
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def load_decision_needed(last_decision_file, threshold_hours=4):
    if os.path.exists(last_decision_file):
        with open(last_decision_file, 'rb') as file:
            last_decision_time = pickle.load(file)
        return (datetime.now() - last_decision_time) > timedelta(hours=threshold_hours)
    return True

def save_decision_time(last_decision_file):
    with open(last_decision_file, 'wb') as file:
        pickle.dump(datetime.now(), file)


def get_user_decision():
    user_decision = input("Do you want to load the data? (yes/no): ").strip().lower()
    if user_decision not in ["yes", "no"]:
        print("Invalid input. Defaulting to load.")
        return True
    return user_decision == "yes"

def scrape_jobs(platform, url, pages=30):
    if platform == 'indeed':
        return scrape_jobs_from_indeed(url, pages)
    elif platform == 'stepstone':
        return scrape_jobs_from_stepstone(url, pages)

def handle_cookies(driver):
    try:
        # Wait for the page to load by waiting for a known element that's always present on the page
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))


        # Try clicking the accept button using different selectors
        accept_button_selectors = [
            (By.ID, 'ccmgt_preferences_accept'),
            (By.ID, 'ccmgt_explicit_accept'),
            (By.XPATH, '//div[contains(@class, "ccmgt_accept_button") and contains(text(), "Alles akzeptieren")]'),
            # XPATH with class and text
            (By.CSS_SELECTOR, '.privacy-prompt-button.primary-button.ccmgt_accept_button'),  # CSS Selector
            (By.ID, 'onetrust-accept-btn-handler'),  # Adding the new button by ID
        ]

        clicked = False
        for by, selector in accept_button_selectors:
            try:
                WebDriverWait(driver, 1).until(EC.element_to_be_clickable((by, selector))).click()
                clicked = True
                print("Cookie button clicked.")
                break  # Exit loop after successful click
            except Exception:
                continue  # Try the next selector if current one fails

        if not clicked:
            print("Failed to click cookie button with provided selectors.")
    except Exception as e:
        print("An exception occurred while handling cookies:", str(e))

def load_config(config_file="config.json"):
    try:
        with open(config_file, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        print("Configuration file not found.")
        return {}
    except json.JSONDecodeError:
        print("Error parsing the configuration file.")
        return {}

def scrape_jobs_from_stepstone(url, pages=1):
    driver = initialize_driver()
    driver.get(url)
    handle_cookies(driver)

    jobs_data = []
    for _ in tqdm(range(pages)):
        job_cards = driver.find_elements(By.XPATH, '//article[@data-at="job-item"]')
        for job_card in job_cards:
            title = job_card.find_element(By.XPATH, './/h2').text
            job_link_element = job_card.find_element(By.XPATH, './/a[@data-at="job-item-title"]')
            job_link = job_link_element.get_attribute('href')

            # Check if the link is relative and prepend the domain if necessary
            if job_link.startswith("/"):
                job_link = domain + job_link
            # Example of scraping job description with a hypothetical class name
            # Attempt to find a description or print part of the HTML for inspection
            try:
                description_element = job_card.find_element(By.XPATH, './/div[@data-at="jobcard-content"]')
                description = description_element.text
            except Exception as e:
                description = "No description available"
            jobs_data.append({'title': title, 'description': description, 'link': job_link})

        # Attempt to go to the next page
        try:
            current_url = driver.current_url
            next_page_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//a[@aria-label="Next"]'))
            )
            next_page_btn.click()
            # Wait for the URL to change or for a specific element that signifies a new page has loaded
            WebDriverWait(driver, 10).until(lambda driver: driver.current_url != current_url)
        except Exception as e:
            print("Error: Navigating to next page failed or last page reached:", str(e))
            print("All found jobs up to now will be saved.")
            return pd.DataFrame(jobs_data)
        time.sleep(2)

    driver.quit()
    return pd.DataFrame(jobs_data)


def scrape_jobs_from_indeed(url, pages=1):
    driver = initialize_driver()
    driver.get(url)
    handle_cookies(driver)

    jobs_data = []
    for _ in tqdm(range(pages)):
        close_popup_if_present(driver)
        time.sleep(4)
        job_cards = driver.find_elements(By.CSS_SELECTOR, 'div.css-dekpa.e37uo190')
        for job_card in job_cards:
            title_element = job_card.find_element(By.CSS_SELECTOR,
                                                  'h2.jobTitle.css-14z7akl.eu4oa1w0 a.jcs-JobTitle.css-jspxzf.eu4oa1w0')
            title = title_element.text
            # Extract the job link
            job_link = title_element.get_attribute('href')
            print(title)
            # Check if the link is relative and prepend the domain if necessary
            if job_link.startswith("/"):
                job_link = domain + job_link
            # Example of scraping job description with a hypothetical class name
            # Attempt to find a description or print part of the HTML for inspection
            jobs_data.append({'title': title, 'description': "", 'link': job_link})

        # Attempt to go to the next page
        try:
            current_url = driver.current_url
            next_page_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//a[@aria-label="Next Page"]'))
            )
            next_page_btn.click()
            # Wait for the URL to change or for a specific element that signifies a new page has loaded
            WebDriverWait(driver, 10).until(lambda driver: driver.current_url != current_url)
        except Exception as e:
            print("Error: Navigating to next page failed or last page reached:", str(e))
            print("All found jobs up to now will be saved.")
            return pd.DataFrame(jobs_data)

    driver.quit()
    return pd.DataFrame(jobs_data)


def close_popup_if_present(driver):
    try:
        # Wait for the popup to appear. Adjust the timeout as needed.
        WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.ID, "mosaic-desktopserpjapopup"))
        )
        # Look for the close button within the popup and click it.
        close_btn = driver.find_element(By.CSS_SELECTOR, 'button[aria-label="schließen"]')
        close_btn.click()
        print("Popup closed successfully.")
    except (TimeoutException, NoSuchElementException):
        # If the popup doesn't appear or the close button is not found, just continue.
        pass


def construct_file_path(folder, filename):
    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Construct the path to the specified folder relative to the script directory
    folder_path = os.path.join(script_dir, folder)

    # Make the folder if it doesn't exist
    os.makedirs(folder_path, exist_ok=True)

    # Construct the full path for the file
    file_path = os.path.join(folder_path, filename)

    # Return the full path ready for use
    return file_path

def create_html_output(filtered_jobs_df, filename):
    # Select only 'title' and 'link' for HTML presentation
    df = filtered_jobs_df[['title', 'link']]

    # Convert 'link' column to HTML anchor tags
    df.loc[:, 'link'] = df['link'].apply(lambda x: f'<a href="{x}">Link</a>')

    # Export to HTML, integrating the CSS and nightmode
    current_hour = datetime.now().hour
    night_mode = current_hour >= 18 or current_hour < 8
    css_filename = "style_dark.css" if night_mode else "style_normal.css"
    css_choice = os.path.join('template', css_filename)

    # Generate HTML for the DataFrame
    html_table = generate_html_table(df)

    # Complete HTML document
    html_output = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Job Listings</title>
        <link rel="stylesheet" type="text/css" href="{css_choice}">
        <script>
        function getSelectedRows() {{
            const selectedIds = [];
            document.querySelectorAll('input[name="rowCheckbox"]:checked').forEach((checkbox) => {{
                selectedIds.push(checkbox.value);
            }});
            alert("Selected IDs: " + selectedIds.join(", "));
        }}
    </script>
    </head>
    <body>
        <h2 style="text-align:center;">Job Listings</h2>
        {html_table}
        <button onclick="getSelectedRows()">Get Selected IDs</button>

    </body>
    </html>
    """
    # Save the HTML file
    with open(filename, "w") as f:
        f.write(html_output)


def generate_html_table(df):
    table_styles = "style='width: 60%; border-collapse: collapse;'"
    html = f"<table {table_styles}>"
    # Add column headers, including one for checkboxes
    html += "<tr>"
    for col in df.columns:
        formatted_col = col.capitalize()  # Capitalize the first letter, rest lowercase
        html += f"<th>{formatted_col}</th>"
    html += "<th>Select</th>"
    html += "</tr>"

    # Add rows with a checkbox in the first column
    for index, row in df.iterrows():
        html += f"<tr>"
        for item in row:
            html += f"<td>{item}</td>"
        html += f"<td><input type='checkbox' name='rowCheckbox' value='{index}'></td>"
        html += "</tr>"

    html += "</table>"
    return html


def filter_and_output_jobs(jobs_df, aligned_titles):
    html_filename = "filtered_jobs.html"

    # Convert job titles in DataFrame to lowercase for case-insensitive matching
    jobs_df['title_lower'] = jobs_df['title'].str.lower()
    # Convert aligned_titles to lowercase
    aligned_titles_lower = [title.lower() for title in aligned_titles]

    # Filter DataFrame to keep rows where 'title_lower' matches any of the aligned titles
    filtered_jobs_df = jobs_df[jobs_df['title_lower'].isin(aligned_titles_lower)]

    # Debug output for titles not found
    found_titles_lower = set(filtered_jobs_df['title_lower'])
    for title in aligned_titles_lower:
        if title not in found_titles_lower:
            print(f"Title not found: {title}")

    filtered_jobs_df = filtered_jobs_df.copy()
    filtered_jobs_df.drop('title_lower', axis=1, inplace=True)


    create_html_output(filtered_jobs_df, html_filename)
    print("Filtering completed. HTML Export done. Opening HTML file in default browser...")
    html_file_path = os.path.abspath(html_filename)
    webbrowser.open('file://' + html_file_path)

def user_confirmation_to_overwrite(filename):
    response = input(f"The file {filename} already exists. Do you want to overwrite it? (y/n): ")
    return response.lower() == 'y'

def main():
    indeed_filename = construct_file_path("data", "indeed_jobs_df.pkl")
    stepstone_filename = construct_file_path("data", "stepstone_jobs_df.pkl")

    parser = argparse.ArgumentParser(description="AI Job scraper script")
    parser.add_argument('--indeed', action='store_true', help='Scrape jobs from Indeed')
    parser.add_argument('--stepstone', action='store_true', help='Scrape jobs from StepStone')
    parser.add_argument('--filter', action='store_true', help='Filter job offers by interests')
    args = parser.parse_args()

    config = load_config()
    openai_api_key = config.get("openai_api_key", "")
    stepstone_url = config.get("stepstone_url", "")
    indeed_url = config.get("indeed_url", "")
    user_interests = config.get("user_interests", [])
    jobs_to_avoid = config.get("jobs_to_avoid", [])

    # Check for existence of job files and handle cases
    indeed_exists = os.path.isfile(indeed_filename)
    stepstone_exists = os.path.isfile(stepstone_filename)

    if args.indeed:
        if indeed_exists and not user_confirmation_to_overwrite(indeed_filename):
            print(f"Skipping scraping for Indeed. {indeed_filename} was not overwritten.")
        else:
            jobs_df = scrape_jobs('indeed', indeed_url)
            jobs_df.to_pickle(indeed_filename)
            print("Finished scraping Indeed and saved jobs to pickle file.")
    elif args.stepstone:
        if stepstone_exists and not user_confirmation_to_overwrite(stepstone_filename):
            print(f"Skipping scraping for StepStone. {stepstone_filename} was not overwritten.")
        else:
            jobs_df = scrape_jobs('stepstone', stepstone_url)
            jobs_df.to_pickle(stepstone_filename)
            print("Finished scraping StepStone and saved jobs to pickle file.")

    else:
        if indeed_exists and stepstone_exists:
            print("Both Indeed and StepStone job files found.")
            choice = input("Specify which one to use ('indeed' or 'stepstone'): ").lower().strip()

            if choice == 'indeed':
                print("Loading Indeed job file.")
                jobs_df = pd.read_pickle(indeed_filename)
            elif choice == 'stepstone':
                print("Loading StepStone job file.")
                jobs_df = pd.read_pickle(stepstone_filename)
            else:
                print("Invalid choice. Exiting.")
                sys.exit()
        elif indeed_exists:
            print("Found Indeed job file.")
            jobs_df = pd.read_pickle(indeed_filename)
        elif stepstone_exists:
            print("Found StepStone job file.")
            jobs_df = pd.read_pickle(stepstone_filename)
        else:
            print("Error: No jobs scraped yet.")
            sys.exit()

        if args.filter:
            job_titles = jobs_df['title'].tolist()
            filtered_titles = filter_job_titles_by_interest(openai_api_key, job_titles, user_interests, jobs_to_avoid)
            print(f"Processing of job titles complete. Keeeping {len(filtered_titles)} jobs.")
            filter_and_output_jobs(jobs_df, filtered_titles)
        else:
            print("Missing arguments.")
            print("""
                Job Scraper Tool Usage Guide:
        
                - Scrape Indeed: Use '--indeed' to scrape job listings from Indeed.
        
                - Scrape StepStone: Use '--stepstone' to scrape job listings from StepStone.
        
                - Filter job offers: After scraping, use '--filter' to keep only job offers which match with the specified interests.
        
                Example Usage:
                  python job_scraper.py --indeed                 # To scrape jobs from Indeed and save the results in jobs.df.
                  python job_scraper.py --stepstone              # To scrape jobs from StepStone and save the results in jobs.df.
                  python job_scraper.py --filter                 # To filter the results based on interests.
        
                Note: These flags can be used individually or combined to customize your job search and data processing workflow.
                """)

    print("Done.")


if __name__ == '__main__':
    main()

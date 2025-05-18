import os
import sys
import glob
import time
import pickle
import json
import hashlib
import traceback
from datetime import datetime, timedelta
from collections import Counter
import argparse
import pandas as pd
import re
from tqdm import tqdm
import streamlit as st
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from gpt_filter import filter_jobs_by_interest
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


def initialize_driver():
    options = Options()
    options.add_argument('--headless')
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

def load_existing_jobs(filename):
    """Load existing jobs from pickle file if it exists."""
    if os.path.exists(filename):
        try:
            return pd.read_pickle(filename)
        except Exception as e:
            print(f"Error loading existing jobs: {e}")
            return pd.DataFrame(columns=['title', 'description', 'link'])
    return pd.DataFrame(columns=['title', 'description', 'link'])

def get_unique_jobs(existing_df, new_df):
    """Compare existing and new jobs, return only unique new jobs."""
    if existing_df.empty:
        return new_df
    
    # Create a set of existing job links for quick lookup
    existing_links = set(existing_df['link'])
    
    # Filter new jobs to only include those not in existing_links
    unique_new_jobs = new_df[~new_df['link'].isin(existing_links)]
    
    print(f"Found {len(unique_new_jobs)} new unique jobs out of {len(new_df)} total jobs")
    return unique_new_jobs

def scrape_jobs_from_stepstone(url, pages=1):
    print("Initializing web driver...")
    driver = initialize_driver()
    print("Opening URL...")
    driver.get(url)
    print("Handling cookie consent...")
    handle_cookies(driver)

    # Extract domain from the URL for relative links
    parsed_url = urlparse(url)
    domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
    base_path = parsed_url.path
    query_dict = parse_qs(parsed_url.query)

    jobs_data = []
    for page in tqdm(range(1, pages + 1)):
        # Set the 'page' parameter in the query string
        query_dict['page'] = [str(page)]
        new_query = urlencode(query_dict, doseq=True)
        new_url = urlunparse((parsed_url.scheme, parsed_url.netloc, base_path, '', new_query, ''))
        driver.get(new_url)
        print("Navigated to:", driver.current_url)
        time.sleep(2) 
        job_cards = driver.find_elements(By.XPATH, '//article[@data-at="job-item"]')
        if not job_cards:
            print(f"No job cards found on page {page}. Stopping pagination.")
            break
        for job in job_cards:
            title = job.find_element(By.XPATH, './/h2').text
            link_el = job.find_element(By.XPATH, './/a[@data-at="job-item-title"]')
            job_link = link_el.get_attribute('href')
            if job_link.startswith('/'):
                job_link = domain + job_link

            # NEW: company name
            try:
                company = job.find_element(
                    By.XPATH, './/span[@data-at="job-item-company-name"]'
                ).text.strip()
            except Exception:
                company = ''

            # NEW: location string (can be several cities separated by commas)
            try:
                location = job.find_element(
                    By.XPATH, './/span[@data-at="job-item-location"]'
                ).text.strip()
            except Exception:
                location = ''

            try:
                description = job.find_element(
                    By.XPATH, './/div[@data-at="jobcard-content"]'
                ).text
            except Exception:
                description = ''

            jobs_data.append({
                'title': title,
                'company': company,
                'location': location,
                'description': description,
                'link': job_link
            })
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
            job_link = title_element.get_attribute('href')
            if job_link.startswith("/"):
                job_link = "https://de.indeed.com" + job_link
            jobs_data.append({'title': title, 'description': "", 'link': job_link})

        try:
            current_url = driver.current_url
            next_page_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//a[@aria-label="Next Page"]'))
            )
            next_page_btn.click()
            WebDriverWait(driver, 10).until(lambda driver: driver.current_url != current_url)
        except Exception as e:
            print("Error: Navigating to next page failed or last page reached:", str(e))
            break

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

def run_streamlit_dashboard(filtered_jobs_df):
    st.set_page_config(page_title="Job Listings", layout="wide")
    st.title("Job Listings")
    st.write(f"{len(filtered_jobs_df)} jobs found.")
    filtered_jobs_df = filtered_jobs_df.reset_index(drop=True)
    filtered_jobs_df['Select'] = False
    # Sort by company name if the column exists
    if 'company' in filtered_jobs_df.columns:
        filtered_jobs_df = filtered_jobs_df.sort_values(by='company', na_position='last').reset_index(drop=True)
    # Show title, company, location, and link in the main table, and make link clickable
    columns = ['title', 'company', 'location', 'link', 'Select']
    # Only include columns that exist in the DataFrame (for backward compatibility)
    columns = [col for col in columns if col in filtered_jobs_df.columns]
    table_df = filtered_jobs_df[columns].copy()
    # Use LinkColumn for clickable links
    selected = st.data_editor(
        table_df,
        use_container_width=True,
        num_rows="dynamic",
        disabled=[col for col in ['title', 'link', 'company', 'location'] if col in table_df.columns],
        column_config={
            "link": st.column_config.LinkColumn("Link", display_text="Open Link")
        } if 'link' in table_df.columns else None
    )
    st.write("Selected job indices:", list(selected[selected['Select']].index))
    for idx, row in selected[selected['Select']].iterrows():
        st.markdown(f"**{row['title']}**  ")
        if 'company' in row:
            st.markdown(f"*Company:* {row['company']}")
        if 'location' in row:
            st.markdown(f"*Location:* {row['location']}")
        st.markdown(f"[Link to job posting]({filtered_jobs_df.loc[idx, 'link']})")
        st.markdown("---")

def filter_and_output_jobs(jobs_df, aligned_titles):
    # Convert job titles in DataFrame to lowercase for case-insensitive matching
    jobs_df['title_lower'] = jobs_df['title'].str.lower()
    aligned_titles_lower = [title.lower() for title in aligned_titles]
    filtered_jobs_df = jobs_df[jobs_df['title_lower'].isin(aligned_titles_lower)]
    found_titles_lower = set(filtered_jobs_df['title_lower'])
    for title in aligned_titles_lower:
        if title not in found_titles_lower:
            print(f"Title not found: {title}")
    filtered_jobs_df = filtered_jobs_df.copy()
    filtered_jobs_df.drop('title_lower', axis=1, inplace=True)
    run_streamlit_dashboard(filtered_jobs_df)

def main():
    indeed_filename = construct_file_path("data", "indeed_jobs_df.pkl")
    stepstone_filename = construct_file_path("data", "stepstone_jobs_df.pkl")

    parser = argparse.ArgumentParser(description="AI Job scraper script")
    parser.add_argument('--indeed', action='store_true', help='Scrape jobs from Indeed')  # Currently disabled
    parser.add_argument('--stepstone', action='store_true', help='Scrape jobs from StepStone')
    parser.add_argument('--filter', action='store_true', help='Filter job offers by interests')
    parser.add_argument('--dashboard', action='store_true', help='Show the dashboard for the latest job file')
    args = parser.parse_args()

    config = load_config()
    openai_api_key = config.get("openai_api_key", "")
    stepstone_url = config.get("stepstone_url", "")
    indeed_url = config.get("indeed_url", "")
    user_interests = config.get("user_interests", [])
    jobs_to_avoid = config.get("jobs_to_avoid", [])
    homeoffice_required = config.get("homeoffice_required", False)

    # Move dashboard logic to the top
    if args.dashboard:
        files = [
            (f, os.path.getmtime(f)) for f in [indeed_filename, stepstone_filename] if os.path.exists(f)
        ]
        if not files:
            print("No job file found. Please run scraping/filtering first.")
            return
        latest_file = max(files, key=lambda x: x[1])[0]
        print(f"Loading jobs from {latest_file}")
        jobs_df = pd.read_pickle(latest_file)
        run_streamlit_dashboard(jobs_df)
        return

    # if args.indeed:
    #     # Load existing jobs
    #     existing_jobs_df = load_existing_jobs(indeed_filename)
    #     # Scrape new jobs
    #     new_jobs_df = scrape_jobs('indeed', indeed_url)
    #     # Get only unique new jobs
    #     unique_new_jobs = get_unique_jobs(existing_jobs_df, new_jobs_df)
    #     # Combine existing and new unique jobs
    #     combined_jobs_df = pd.concat([existing_jobs_df, unique_new_jobs], ignore_index=True)
    #     # Save combined jobs
    #     combined_jobs_df.to_pickle(indeed_filename)
    #     print(f"Added {len(unique_new_jobs)} new jobs to Indeed database. Total jobs: {len(combined_jobs_df)}")
    #     jobs_df = combined_jobs_df
    #     # Indeed scraping is currently disabled due to Cloudflare protection.
    #     # Only StepStone scraping is supported at this time.
    #     return

    elif args.stepstone:
        # Load existing jobs
        existing_jobs_df = load_existing_jobs(stepstone_filename)
        # Scrape new jobs
        new_jobs_df = scrape_jobs('stepstone', stepstone_url)
        # Get only unique new jobs
        unique_new_jobs = get_unique_jobs(existing_jobs_df, new_jobs_df)
        # Combine existing and new unique jobs
        combined_jobs_df = pd.concat([existing_jobs_df, unique_new_jobs], ignore_index=True)
        # Save combined jobs
        combined_jobs_df.to_pickle(stepstone_filename)
        print(f"Added {len(unique_new_jobs)} new jobs to StepStone database. Total jobs: {len(combined_jobs_df)}")
        jobs_df = combined_jobs_df
    else:
        # Default to StepStone if no argument is given
        print("Defaulting to StepStone job file.")
        jobs_df = pd.read_pickle(stepstone_filename)

    if args.filter:
        jobs_list = jobs_df[['title', 'description']].to_dict(orient='records')
        filtered_titles = filter_jobs_by_interest(openai_api_key, jobs_list, user_interests, jobs_to_avoid, homeoffice_required)
        print(f"Processing of jobs complete. Keeping {len(filtered_titles)} jobs.")
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

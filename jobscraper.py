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
import sqlite3


def initialize_database(db_path="data/jobs.db"):
    """
    Centralized database initialization and schema management.
    Creates the normalized schema with jobs and job_filters tables.
    """
    # Ensure the data directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Create jobs table (single source of truth)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                company TEXT,
                location TEXT,
                description TEXT,
                link TEXT,
                source TEXT DEFAULT 'stepstone',
                deleted INTEGER DEFAULT 0,
                analyzed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(title, company)
            )
        ''')
        
        # Create job_filters table (for filter results)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS job_filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                filter_type TEXT NOT NULL,
                value INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs (id),
                UNIQUE(job_id, filter_type)
            )
        ''')
        
        conn.commit()
        print(f"Database initialization complete. Normalized schema ready at {db_path}")


def get_jobs_from_db(filter_type=None, db_path="data/jobs.db", include_deleted=False):
    """
    Centralized function to load jobs from database with optional filtering.
    
    Args:
        filter_type: None for all jobs, 'step2_homeoffice', 'step3_interest', etc.
        db_path: Path to database
        include_deleted: Whether to include deleted jobs
    
    Returns:
        DataFrame with job data
    """
    if not os.path.exists(db_path):
        return pd.DataFrame(columns=['id', 'title', 'company', 'location', 'description', 'link', 'deleted', 'analyzed'])
    
    with sqlite3.connect(db_path) as conn:
        try:
            if filter_type is None:
                # Get all jobs
                if include_deleted:
                    query = "SELECT * FROM jobs"
                else:
                    query = "SELECT * FROM jobs WHERE deleted = 0"
            else:
                # Get jobs with specific filter
                if include_deleted:
                    query = """
                        SELECT j.* FROM jobs j
                        JOIN job_filters jf ON j.id = jf.job_id
                        WHERE jf.filter_type = ? AND jf.value = 1
                    """
                else:
                    query = """
                        SELECT j.* FROM jobs j
                        JOIN job_filters jf ON j.id = jf.job_id
                        WHERE jf.filter_type = ? AND jf.value = 1 AND j.deleted = 0
                    """
                return pd.read_sql(query, conn, params=[filter_type])
            
            return pd.read_sql(query, conn)
        except Exception as e:
            print(f"Error loading jobs: {e}")
            return pd.DataFrame(columns=['id', 'title', 'company', 'location', 'description', 'link', 'deleted', 'analyzed'])


def initialize_driver():
    options = Options()
    options.add_argument('--headless')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

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

def load_existing_jobs(db_path="data/jobs.db"):
    """Load existing jobs from the jobs table."""
    return get_jobs_from_db(filter_type=None, db_path=db_path, include_deleted=True)

def get_unique_jobs(existing_df, new_df):
    """Compare existing and new jobs, return only unique new jobs based on (title, company)."""
    if existing_df.empty:
        return new_df
    
    # Create a set of existing (title, company) pairs for deduplication
    existing_title_company = set()
    for _, row in existing_df.iterrows():
        existing_title_company.add((row['title'], row['company']))
    
    # Filter new jobs to only include those not in existing_title_company
    unique_new_jobs = []
    for _, row in new_df.iterrows():
        if (row['title'], row['company']) not in existing_title_company:
            unique_new_jobs.append(row)
    
    unique_new_jobs_df = pd.DataFrame(unique_new_jobs) if unique_new_jobs else pd.DataFrame(columns=new_df.columns)
    
    print(f"Found {len(unique_new_jobs_df)} new unique jobs out of {len(new_df)} total jobs")
    return unique_new_jobs_df

def scrape_jobs_from_stepstone(url, pages=1, db_path="data/jobs.db"):
    print("Initializing web driver...")
    driver = initialize_driver()
    print("Opening URL...")
    driver.get(url)
    print("Handling cookie consent...")
    handle_cookies(driver)

    # Load existing title+company pairs from DB to avoid duplicates
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT title, company FROM jobs WHERE deleted = 0 OR deleted IS NULL")
        existing_title_company = set((row[0], row[1]) for row in cur.fetchall())

    # Extract domain from the URL for relative links
    parsed_url = urlparse(url)
    domain = f"{parsed_url.scheme}://{parsed_url.netloc}"

    jobs_data = []
    with sqlite3.connect(db_path) as conn:
        for page in tqdm(range(1, pages + 1)):
            query_dict = parse_qs(parsed_url.query)
            query_dict['page'] = [str(page)]
            new_query = urlencode(query_dict, doseq=True)
            new_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', new_query, ''))
            driver.get(new_url)
            print("Navigated to:", driver.current_url)
            time.sleep(2)
            job_cards = driver.find_elements(By.XPATH, '//article[@data-at="job-item"]')
            if not job_cards:
                print(f"No job cards found on page {page}. Stopping pagination.")
                break
            # --- Print how many jobs on this page are not yet in DB (by title+company) ---
            page_title_company = set()
            for job in job_cards:
                title = job.find_element(By.XPATH, './/h2').text
                try:
                    company = job.find_element(By.XPATH, './/span[@data-at="job-item-company-name"]').text.strip()
                except Exception:
                    company = ''
                page_title_company.add((title, company))
            new_jobs = [tc for tc in page_title_company if tc not in existing_title_company]
            print(f"Page {page}: {len(new_jobs)} jobs (by title+company) are not yet in the DB and will be processed.")
            print("Processing job cards...")
            driver.execute_script("window.open('');")
            detail_window = driver.window_handles[-1]
            main_window = driver.current_window_handle
            for job in tqdm(job_cards):
                title = job.find_element(By.XPATH, './/h2').text
                link_el = job.find_element(By.XPATH, './/a[@data-at="job-item-title"]')
                job_link = link_el.get_attribute('href')
                if job_link.startswith('/'):
                    job_link = domain + job_link
                try:
                    company = job.find_element(By.XPATH, './/span[@data-at="job-item-company-name"]').text.strip()
                except Exception:
                    company = ''
                # Skip if already in DB by (title, company)
                if (title, company) in existing_title_company:
                    continue
                try:
                    location = job.find_element(By.XPATH, './/span[@data-at="job-item-location"]').text.strip()
                except Exception:
                    location = ''
                full_description = ''
                try:
                    driver.switch_to.window(detail_window)
                    driver.get(job_link)
                    try:
                        WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.TAG_NAME, 'article'))
                        )
                    except Exception:
                        print(f"Error loading detail page for {job_link}")
                        pass
                    time.sleep(1.5)
                    divs = driver.find_elements(By.TAG_NAME, 'div')
                    div_texts = [d.text for d in divs if d.text and len(d.text) > 500]
                    if div_texts:
                        full_description = sorted(div_texts, key=len, reverse=True)[0]
                    else:
                        full_description = driver.find_element(By.TAG_NAME, 'body').text
                    driver.switch_to.window(main_window)
                except Exception as e:
                    print(f"Fehler beim Laden der Detailseite: {e}")
                    full_description = ''
                    driver.switch_to.window(main_window)
                job_entry = {
                    'title': title,
                    'company': company,
                    'location': location,
                    'description': full_description,
                    'link': job_link
                }
                jobs_data.append(job_entry)
                # Write to DB immediately using new schema
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO jobs (title, company, location, description, link, source) VALUES (?, ?, ?, ?, ?, 'stepstone')",
                        (title, company, location, full_description, job_link)
                    )
                    conn.commit()
                    existing_title_company.add((title, company))
                except Exception as e:
                    print(f"DB insert error for {job_link}: {e}")
            driver.switch_to.window(detail_window)
            driver.close()
            driver.switch_to.window(main_window)
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

@st.cache_resource
def init_db_once(db_path):
    """Initialize database only once per session"""
    initialize_database(db_path)
    return True

def run_streamlit_dashboard(jobs_df=None, db_path="data/jobs.db"):
    st.set_page_config(page_title="Job Listings", layout="wide")
    st.title("Job Listings")

    # Initialize database only once per session
    init_db_once(db_path)

    # Load filtered job data using centralized function
    filtered_jobs_step2_df = get_jobs_from_db("step2_homeoffice", db_path)
    filtered_jobs_step3_df = get_jobs_from_db("step3_interest", db_path)
    
    # Category selector
    options = ["All Jobs"]
    if not filtered_jobs_step2_df.empty:
        options.append("Home Office Jobs (Step 2)")
    if not filtered_jobs_step3_df.empty:
        options.append("Interest Filtered Jobs (Step 3)")
    
    selected_category = st.radio("Select job category to display:", options, index=len(options)-1)

    if selected_category == "Interest Filtered Jobs (Step 3)" and not filtered_jobs_step3_df.empty:
        display_df = filtered_jobs_step3_df.copy()
        st.write(f"{len(display_df)} interest-filtered jobs found.")
    elif selected_category == "Home Office Jobs (Step 2)" and not filtered_jobs_step2_df.empty:
        display_df = filtered_jobs_step2_df.copy()
        st.write(f"{len(display_df)} home-office jobs found.")
    else:
        if jobs_df is None:
            # Default to all jobs using centralized function
            jobs_df = get_jobs_from_db(filter_type=None, db_path=db_path)
        display_df = jobs_df.copy()
        st.write(f"{len(display_df)} jobs found.")

    # Ensure the deleted column exists in the display DataFrame
    if 'deleted' not in display_df.columns:
        display_df['deleted'] = 0

    display_df = display_df.reset_index(drop=True)
    display_df['Select'] = False
    # Sort by company name if the column exists
    if 'company' in display_df.columns:
        display_df = display_df.sort_values(by='company', na_position='last').reset_index(drop=True)
    # Show title, company, location, and link in the main table, and make link clickable
    columns = ['title', 'company', 'location', 'link', 'Select']
    columns = [col for col in columns if col in display_df.columns]
    table_df = display_df[columns].copy()
    selected = st.data_editor(
        table_df,
        use_container_width=True,
        num_rows="dynamic",
        disabled=[col for col in ['title', 'link', 'company', 'location'] if col in table_df.columns],
        column_config={
            "link": st.column_config.LinkColumn("Link", display_text="Open Link")
        } if 'link' in table_df.columns else None
    )
    
    # Delete selected jobs
    selected_indices = list(selected[selected['Select']].index)
    st.write("Selected job indices:", selected_indices)
    
    if selected_indices and st.button("Mark Selected Jobs as Deleted"):
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            for idx in selected_indices:
                # Get job ID or use title+company for identification
                if 'id' in display_df.columns:
                    job_id = int(display_df.loc[idx, 'id'])
                    cursor.execute("UPDATE jobs SET deleted = 1 WHERE id = ?", (job_id,))
                else:
                    # Fallback to title+company identification
                    title = display_df.loc[idx, 'title']
                    company = display_df.loc[idx, 'company']
                    cursor.execute("UPDATE jobs SET deleted = 1 WHERE title = ? AND company = ?", (title, company))
            
            conn.commit()
        
        st.success(f"Marked {len(selected_indices)} job(s) as deleted")
        st.rerun()
    
    # Display selected job details
    for idx, row in selected[selected['Select']].iterrows():
        st.markdown(f"**{row['title']}**  ")
        if 'company' in row:
            st.markdown(f"*Company:* {row['company']}")
        if 'location' in row:
            st.markdown(f"*Location:* {row['location']}")
        st.markdown(f"[Link to job posting]({display_df.loc[idx, 'link']})")
        st.markdown("---")

def filter_and_output_jobs(jobs_df, filter_results, db_path="data/jobs.db"):
    """
    Update job filter results in the job_filters table
    
    filter_results: Tuple of (step1_titles, step2_titles, step3_titles) from the filter_jobs_by_interest function
    """
    step1_titles, step2_titles, step3_titles = filter_results
    
    # Create a proper copy to avoid SettingWithCopyWarning
    jobs_df = jobs_df.copy()
    
    # Convert job titles in DataFrame to lowercase for case-insensitive matching
    jobs_df['title_lower'] = jobs_df['title'].str.lower()
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Process step 2 filtered jobs (home office filtered)
        step2_titles_lower = [title.lower() for title in step2_titles]
        step2_jobs = jobs_df[jobs_df['title_lower'].isin(step2_titles_lower)]
        found_titles_lower = set(step2_jobs['title_lower'])
        for title in step2_titles_lower:
            if title not in found_titles_lower:
                print(f"Step 2 - Title not found: {title}")
        
        # Update job_filters table for step 2
        for _, job in step2_jobs.iterrows():
            if 'id' in job:
                job_id = int(job['id'])  
            else:
                # Find job_id by title+company
                cursor.execute("SELECT id FROM jobs WHERE title = ? AND company = ?", (job['title'], job['company']))
                result = cursor.fetchone()
                if result:
                    job_id = result[0]
                else:
                    continue
            
            cursor.execute("""
                INSERT OR REPLACE INTO job_filters (job_id, filter_type, value)
                VALUES (?, 'step2_homeoffice', 1)
            """, (job_id,))
        
        # Process step 3 filtered jobs (interest filtered)
        step3_titles_lower = [title.lower() for title in step3_titles]
        step3_jobs = jobs_df[jobs_df['title_lower'].isin(step3_titles_lower)]
        found_titles_lower = set(step3_jobs['title_lower'])
        for title in step3_titles_lower:
            if title not in found_titles_lower:
                print(f"Step 3 - Title not found: {title}")
        
        # Update job_filters table for step 3
        for _, job in step3_jobs.iterrows():
            if 'id' in job:
                job_id = int(job['id'])  
            else:
                # Find job_id by title+company
                cursor.execute("SELECT id FROM jobs WHERE title = ? AND company = ?", (job['title'], job['company']))
                result = cursor.fetchone()
                if result:
                    job_id = result[0]
                else:
                    continue
            
            cursor.execute("""
                INSERT OR REPLACE INTO job_filters (job_id, filter_type, value)
                VALUES (?, 'step3_interest', 1)
            """, (job_id,))
        
        conn.commit()
    
    print(f"Step 2 filtered jobs (homeoffice): {len(step2_jobs)} jobs marked in job_filters")
    print(f"Step 3 filtered jobs (interests): {len(step3_jobs)} jobs marked in job_filters")

def get_experience_terms(level):
    """
    Convert experience level setting to include/exclude terms.
    Returns a dict with terms to include and exclude.
    """
    experience_mapping = {
        "junior": {
            "include": ["junior","entry-level", "graduate", "trainee", "0-2 years", "0-1 years"],
            "exclude": ["senior", "expert", "lead", "staff", "principal", "architect", "manager", "director", 
                      "several years of work experience"]
        },
        "mid": {
            "include": ["intermediate", "mid-level", "mid level", "associate", "2-4 years", "3-5 years"],
            "exclude": ["senior", "expert", "principal", "lead", "junior", "entry level", "entry-level", 
                      "graduate", "trainee", "8+ years", "10+ years"]
        },
        "senior": {
            "include": ["senior", "expert", "lead", "staff", "architect", "5+ years", "7+ years"],
            "exclude": ["junior", "entry level", "entry-level", "graduate", "trainee", "0-2 years", "internship"]
        },
        "any": {
            "include": [],
            "exclude": []
        }
    }
    
    # Default to "any" if the specified level is not found
    return experience_mapping.get(level.lower(), experience_mapping["any"])

def main():
    db_path = "data/jobs.db"
    
    parser = argparse.ArgumentParser(description="AI Job scraper script")
    parser.add_argument('--indeed', action='store_true', help='Scrape jobs from Indeed')  # Currently disabled
    parser.add_argument('--stepstone', action='store_true', help='Scrape jobs from StepStone')
    parser.add_argument('--filter', action='store_true', help='Filter job offers by interests')
    parser.add_argument('--dashboard', action='store_true', help='Show the dashboard for the latest job file')
    args = parser.parse_args()

    # Initialize database schema for non-dashboard operations
    if not args.dashboard:
        initialize_database(db_path)

    config = load_config()
    openai_api_key = config.get("openai_api_key", "")
    stepstone_url = config.get("stepstone_url", "")
    indeed_url = config.get("indeed_url", "")
    user_interests = config.get("user_interests", [])
    experience_level = config.get("experience_level", "any")
    custom_exclude_terms = config.get("custom_exclude_terms", [])
    homeoffice_required = config.get("homeoffice_required", False)
    
    # Get experience-based terms
    experience_terms = get_experience_terms(experience_level)
    
    # Combine custom exclude terms with experience-based exclude terms
    jobs_to_avoid = experience_terms["exclude"] + custom_exclude_terms
    
    # Include terms will be used to refine job filtering
    jobs_to_include = experience_terms["include"]

    if args.dashboard:
        run_streamlit_dashboard(db_path=db_path)
        return

    if args.stepstone:
        existing_jobs_df = load_existing_jobs(db_path)
        new_jobs_df = scrape_jobs('stepstone', stepstone_url)
        unique_new_jobs = get_unique_jobs(existing_jobs_df, new_jobs_df)
        print(f"Added {len(unique_new_jobs)} new jobs to database.")
        # Jobs are already inserted during scraping, so just load all jobs
        jobs_df = load_existing_jobs(db_path)
        print(f"Total jobs in database: {len(jobs_df)}")
    else:
        # Default to all jobs if no argument is given
        jobs_df = load_existing_jobs(db_path)

    if args.filter:
        if 'deleted' in jobs_df.columns:
            # Only filter jobs that are not marked asdeleted
            jobs_with_filter = jobs_df[jobs_df['deleted'].fillna(0) == 0]
        else:
            # If deleted column doesn't exist, use all jobs
            jobs_with_filter = jobs_df
            
        jobs_list = jobs_with_filter[['id', 'title', 'description', 'company']].to_dict(orient='records')
        filter_results = filter_jobs_by_interest(openai_api_key, jobs_list, user_interests, jobs_to_avoid, homeoffice_required, jobs_to_include, experience_level, db_path)
        print(f"Processing of jobs complete:")
        print(f"  - Step 1 (Basic filtering): {len(filter_results[0])} jobs")
        print(f"  - Step 2 (Home office filtered): {len(filter_results[1])} jobs")
        print(f"  - Step 3 (Interest filtered): {len(filter_results[2])} jobs")
        filter_and_output_jobs(jobs_with_filter, filter_results, db_path)
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

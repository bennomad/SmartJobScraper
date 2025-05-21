# Smart Job Scraper

Smart Job Scraper is a powerful tool designed to streamline the job search process. By leveraging advanced web scraping techniques and AI-powered filtering, this script fetches job listings from Stepstone (and previously Indeed), then filters them based on user-defined interests and criteria.

> **Note:** Scraping from Indeed is currently **not working** as Indeed has implemented a Cloudflare check that blocks automated access. Only Stepstone scraping is supported at this time.

## Installation

This project requires Python 3.6+ and several third-party libraries. You can install the necessary dependencies using pip:

```bash
pip install openai pandas selenium tqdm webdriver-manager
```

- **Chrome Browser**: Ensure you have the latest version of Chrome installed on your computer as this script uses Selenium with ChromeDriver for web scraping. Chrome will run in non-headless mode, meaning a browser window will visibly open and navigate through the sites during the scraping process. This approach is used as headless mode can sometimes cause issues with site interactions. 
  
## Getting Started

### Step 1: Basic Setup

1. **Scraping URLs Setup**: Manually navigate to Stepstone (and previously Indeed) websites in your browser. Apply basic filters according to your preferences and copy the URLs into the `config.json` file under `stepstone_url` (and `indeed_url` if/when supported again).

### Step 2: OpenAI API Setup

1. **OpenAI Registration**: If you haven't already, register at [platform.openai.com](https://platform.openai.com/). Add credits to your account for API usage ($5 should suffice for extensive job searches).

2. **Configuration**: Add your OpenAI API key and your specific job interests to the `config.json` file. Here is what your `config.json` might look like:

    ```json
    {
      "openai_api_key": "your_secret_key_here",
      "stepstone_url": "https://www.stepstone.de/...",
      "indeed_url": "https://de.indeed.com/...",
      "user_interests": ["IT", "Software Development"],
      "jobs_to_avoid": ["senior", "expert", "internship", "educational training", "Data Analysis", "SAP"]
    }
    ```

### Step 3: Running the Scraper

- **Indeed Scraping**: To scrape jobs from Indeed, use the `--indeed` flag:

    ```bash
    python3 jobscraper.py --indeed
    ```
    > **Currently not working:** Indeed scraping is disabled due to Cloudflare protection. This feature will be restored if a workaround is found.

- **Stepstone Scraping**: To scrape jobs from Stepstone, use the `--stepstone` flag:

    ```bash
    python3 jobscraper.py --stepstone
    ```

- **Filtering Jobs**: To filter all job results based on interests with AI-powered analysis, use the `--filter` flag:

    ```bash
    python3 jobscraper.py --filter
    ```
After the scraping and filtering process completes, the results will be compiled into an HTML file, which will automatically be opened in your default web browser for easy viewing.

## General Information and Disclaimer

This project is intended for personal use and educational purposes. Scraping websites can be against their terms of service. Please use this tool responsibly and ethically, respecting the websites' terms and conditions. The developer assumes no responsibility for any misuse of this software or any violations of terms of service.

## Configuration

Edit the `config.json` file to customize your job search:

```json
{
    "openai_api_key": "your-api-key",
    
    "stepstone_url": "https://www.stepstone.de/jobs/your-search-query",
    "indeed_url": "https://de.indeed.com/jobs?q=YourQuery",
  
    "user_interests": ["devops", "docker", "gitlab"],
    "experience_level": "junior",
    "custom_exclude_terms": ["educational training"],
    "homeoffice_required": true
}
```

### Configuration Options

- **openai_api_key**: Your OpenAI API key for filtering jobs
- **stepstone_url**: URL to scrape from Stepstone
- **indeed_url**: URL to scrape from Indeed
- **user_interests**: List of technical skills or areas you're interested in
- **experience_level**: Your target experience level, options:
  - `junior`: Targets entry-level positions, avoids senior roles
  - `mid`: Targets mid-level positions
  - `senior`: Targets senior positions, avoids junior roles
  - `any`: No filtering by experience level
- **custom_exclude_terms**: Additional terms to exclude from job listings
- **homeoffice_required**: If true, only shows remote positions

## Usage

Run the job scraper with:

```
# Scrape from StepStone
python jobscraper.py --stepstone

# Filter jobs based on configuration
python jobscraper.py --filter

# View jobs in the dashboard
python jobscraper.py --dashboard
```

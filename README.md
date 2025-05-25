# Smart Job Scraper

Smart Job Scraper is a powerful tool designed to streamline the job search process. By leveraging advanced web scraping techniques and AI-powered filtering, this script fetches job listings from Stepstone, stores them in a SQLite database, and filters them based on user-defined interests and criteria.

> **Note:** Scraping from Indeed is currently **not working** as Indeed has implemented a Cloudflare check that blocks automated access. Only Stepstone scraping is supported at this time.

## Features

- **Web Scraping**: Automated job scraping from Stepstone with duplicate detection
- **SQLite Database**: Persistent storage of job data with automatic schema management
- **AI-Powered Filtering**: Three-step filtering process using OpenAI GPT models:
  1. Basic filtering to remove unwanted job categories
  2. Home office/remote work filtering (optional)
  3. Interest-based filtering aligned with your skills and preferences
- **Interactive Dashboard**: Streamlit-based web interface for browsing and managing jobs
- **Experience Level Targeting**: Automatic filtering based on experience level (junior, mid, senior)
- **Job Management**: Mark jobs as deleted to hide them from future views

## Installation

This project requires Python 3.6+ and several third-party libraries. You can install the necessary dependencies using pip:

```bash
pip install openai pandas selenium tqdm webdriver-manager streamlit
```

Alternatively, install from the requirements file:

```bash
pip install -r requirements.txt
```

**Additional Requirements:**
- **Chrome Browser**: Ensure you have the latest version of Chrome installed as this script uses Selenium with ChromeDriver for web scraping. The browser runs in headless mode for automated scraping.

## Getting Started

### Step 1: Configuration Setup

Create a `config.json` file in the project directory with your settings:

```json
{
    "openai_api_key": "your-openai-api-key",
    "stepstone_url": "https://www.stepstone.de/jobs/your-search-query",
    "user_interests": ["devops", "docker", "gitlab", "python", "ansible"],
    "experience_level": "junior",
    "custom_exclude_terms": ["educational training"],
    "homeoffice_required": true
}
```

### Step 2: OpenAI API Setup

1. **OpenAI Registration**: Register at [platform.openai.com](https://platform.openai.com/) and add credits to your account ($5 should suffice for extensive job searches).

2. **Get API Key**: Generate an API key and add it to your `config.json` file.

### Step 3: Stepstone URL Setup

1. Navigate to [Stepstone](https://www.stepstone.de/) in your browser
2. Apply your desired filters (location, job type, etc.)
3. Copy the resulting URL and paste it into the `stepstone_url` field in your `config.json`

## Configuration Options

### Required Settings
- **openai_api_key**: Your OpenAI API key for AI-powered job filtering
- **stepstone_url**: URL from Stepstone with your search criteria applied

### Optional Settings
- **user_interests**: List of technical skills or areas you're interested in (e.g., ["python", "docker", "kubernetes"])
- **experience_level**: Target experience level with automatic filtering:
  - `"junior"`: Entry-level positions, excludes senior roles
  - `"mid"`: Mid-level positions
  - `"senior"`: Senior positions, excludes junior roles  
  - `"any"`: No experience-based filtering (default)
- **custom_exclude_terms**: Additional terms to exclude from job listings
- **homeoffice_required**: Set to `true` to only show remote/home office positions

## Usage

### Basic Workflow

1. **Scrape Jobs**: Collect new job listings from Stepstone
   ```bash
   python jobscraper.py --stepstone
   ```

2. **Filter Jobs**: Apply AI-powered filtering based on your interests
   ```bash
   python jobscraper.py --filter
   ```

3. **View Dashboard**: Browse filtered jobs in an interactive web interface
   ```bash
   streamlit run jobscraper.py -- --dashboard
   ```

### Command Line Options

- `--stepstone`: Scrape new jobs from Stepstone and add to database
- `--filter`: Filter existing jobs using AI based on configuration
- `--dashboard`: Launch interactive Streamlit dashboard
- `--indeed`: *(Currently disabled)* Scrape from Indeed

### Dashboard Features

The Streamlit dashboard provides:
- **Job Categories**: View all jobs, home office filtered jobs, or interest-filtered jobs
- **Interactive Table**: Browse jobs with clickable links
- **Job Management**: Select and mark jobs as deleted
- **Detailed View**: Expand job details including company, location, and description
- **Sorting**: Jobs are automatically sorted by company name

## Data Storage

Jobs are stored in a SQLite database (`data/jobs.db`) with a normalized schema:
- `jobs`: Single source of truth for all job data with unique constraint on (title, company)
- `job_filters`: Filter results linked to jobs via foreign keys

The database automatically handles:
- Duplicate detection based on (title, company) combination
- Schema migrations and updates
- Soft deletion (jobs marked as deleted are hidden but preserved)
- Extensible filter types without schema changes

## AI Filtering Process

The filtering system uses a three-step approach:

1. **Step 1 - Basic Filtering**: Removes jobs containing unwanted terms or categories
2. **Step 2 - Home Office Filtering** *(optional)*: Identifies jobs that are clearly 100% remote/home office
3. **Step 3 - Interest Filtering**: Matches jobs to your specified interests and skills

Each step uses GPT-4 mini for intelligent analysis of job titles and descriptions.

## Troubleshooting

### Common Issues

- **Chrome Driver Issues**: The script automatically downloads the appropriate ChromeDriver version
- **API Rate Limits**: The filtering process uses batching to stay within OpenAI rate limits
- **Database Errors**: The database schema is automatically initialized and migrated

### Debug Information

The script generates prompt files (`prompt_step1.txt`, `prompt_step2.txt`, `prompt_step3.txt`) showing the exact prompts sent to the AI for debugging filtering results.

## Legal Disclaimer

This project is intended for personal use and educational purposes. Web scraping may be against some websites' terms of service. Please use this tool responsibly and ethically, respecting websites' terms and conditions and rate limits. The developer assumes no responsibility for any misuse of this software or violations of terms of service.

## Contributing

Feel free to submit issues and enhancement requests. This project is designed to be easily extensible for additional job sites and filtering criteria.

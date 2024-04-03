# Smart Job Scraper

Smart Job Scraper is a powerful tool designed to streamline the job search process. By leveraging advanced web scraping techniques and AI-powered filtering, this script fetches job listings from Indeed and Stepstone, then filters them based on user-defined interests and criteria.

## Installation

This project requires Python 3.6+ and several third-party libraries. You can install the necessary dependencies using pip:

```bash
pip install openai pandas selenium tqdm webdriver-manager
```

## Getting Started

### Step 1: Basic Setup

1. **Scraping URLs Setup**: Manually navigate to Stepstone and Indeed websites in your browser. Apply basic filters according to your preferences and copy the URLs into the `config.json` file under `stepstone_url` and `indeed_url`.

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

- **Stepstone Scraping**: To scrape jobs from Stepstone, use the `--stepstone` flag:

    ```bash
    python3 jobscraper.py --stepstone
    ```

- **Filtering Jobs**: To filter all job results based on interests with AI-powered analysis, use the `--filter` flag:

    ```bash
    python3 jobscraper.py --filter
    ```

## General Information and Disclaimer

This project is intended for personal use and educational purposes. Scraping websites can be against their terms of service. Please use this tool responsibly and ethically, respecting the websites' terms and conditions. The developer assumes no responsibility for any misuse of this software or any violations of terms of service.

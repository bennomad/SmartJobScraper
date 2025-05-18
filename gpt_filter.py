from openai import OpenAI
import os
from tqdm import tqdm
import sys

def filter_jobs_by_interest(openai_api_key, jobs, user_interests, jobs_to_avoid):
    """
    jobs: list of dicts, each with 'title' and 'description'
    Returns: dict with keys 'home_office' and 'other', each a list of job titles.
    """
    client = OpenAI(api_key=openai_api_key)

    print("Total jobs:", len(jobs))
    batch_size = 40  # Reduce batch size for more context
    batches = [jobs[i:i + batch_size] for i in range(0, len(jobs), batch_size)]
    print(f"Splitting the total jobs into {len(batches)} API requests.")

    all_home_office = []
    all_other = []

    print("Processing jobs (title + description)...")
    for batch in tqdm(batches, desc="Filtering Progress"):
        job_entries = [f"Title: {job['title']} || Description: {job['description']}" for job in batch]
        jobs_str = " | ".join(job_entries)
        interests_str = ", ".join(user_interests)
        jobs_to_avoid_str = " , ".join(jobs_to_avoid)

        prompt_message = (
            f"Given the user's interests are in {interests_str}, and aiming to avoid positions such as {jobs_to_avoid_str}, "
            f"carefully review the following job listings, each separated by a pipe symbol. Each listing is formatted as 'Title: ... || Description: ...': {jobs_str}. "
            "Please separate the job titles into two categories, each as a pipe-separated list:\n"
            "1. home_office: Only include job titles where it is very likely (based on strong cues in title or description) that 100% home office or fully remote work is possible. Only include if the job is clearly 100% remote, e.g., phrases like '100% home office', 'fully remote', 'remote only', 'work from anywhere', 'remote-first', 'remote possible for all tasks', etc. If in doubt, do NOT include.\n"
            "2. other: All other job titles that match the user's interests and do not fall into the avoidance categories, but are not clearly 100% home office.\n"
            "Exclude titles only if they are clearly unrelated or are listed in the categories to avoid.\n"
            "Return your answer as JSON with two keys: 'home_office' and 'other', each containing a pipe-separated string of job titles."
        )
        try:
            response = client.chat.completions.create(
                model="gpt-4-0125-preview",
                messages=[
                    {"role": "system",
                     "content": (
                        "You are a helpful assistant. Each job listing is separated by a pipe symbol and contains a title and description. "
                        "Your task is to identify job titles that align with the user's specified interests, no matter how tangentially, and to avoid suggesting titles in the specified categories to avoid. "
                        "You must separate the job titles into two categories: 'home_office' (only if 100% remote is very likely, based on strong cues in title/description, e.g., 'fully remote', 'remote only', '100% home office', 'work from anywhere', 'remote-first', 'remote possible for all tasks', etc. If in doubt, do NOT include) and 'other' (all other jobs matching interests but not clearly 100% remote). "
                        "Return your answer as JSON with two keys: 'home_office' and 'other', each containing a pipe-separated string of job titles."
                    )},
                    {"role": "user", "content": prompt_message}
                ]
            )
            import json as _json
            content = response.choices[0].message.content.strip()
            # Try to parse the JSON from the response
            try:
                result = _json.loads(content)
                home_office = [title.strip().rstrip('.') for title in result.get('home_office', '').split('|') if title.strip()]
                other = [title.strip().rstrip('.') for title in result.get('other', '').split('|') if title.strip()]
            except Exception:
                # fallback: try to extract lists manually if JSON parsing fails
                home_office = []
                other = []
            all_home_office.extend(home_office)
            all_other.extend(other)
        except Exception as e:
            print(f"An error occurred while processing a batch: {e}")
            sys.exit()

    return {"home_office": all_home_office, "other": all_other}
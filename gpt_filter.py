from openai import OpenAI
import os
from tqdm import tqdm
import sys

def filter_jobs_by_interest(openai_api_key, jobs, user_interests, jobs_to_avoid, homeoffice_required=False):
    """
    jobs: list of dicts, each with 'title' and 'description'
    homeoffice_required: if True, only keep jobs that are very likely 100% home office/remote
    """
    client = OpenAI(api_key=openai_api_key)

    print("Total jobs:", len(jobs))
    batch_size = 50  # Reduce batch size since descriptions are longer
    batches = [jobs[i:i + batch_size] for i in range(0, len(jobs), batch_size)]
    print(f"Splitting the total jobs into {len(batches)} API requests.")

    all_filtered_titles = []

    print("Processing jobs (title + description)...")
    for batch in tqdm(batches, desc="Filtering Progress"):
        job_entries = [f"Title: {job['title']} || Description: {job['description']}" for job in batch]
        jobs_str = " | ".join(job_entries)
        interests_str = ", ".join(user_interests)
        jobs_to_avoid_str = " , ".join(jobs_to_avoid)

        if homeoffice_required:
            homeoffice_instruction = (
                "Additionally, ONLY include job titles where it is VERY LIKELY that the job can be performed 100% from home (full remote). "
                "Be strict: Use all clues from the title and description, including synonyms and phrases like 'remote', 'work from anywhere', 'fully distributed', 'home office', '100% remote', 'completely remote', 'work from home', etc. "
                "If there is any doubt, or if the job is only partially remote, hybrid, or the remote status is unclear, EXCLUDE the job. "
                "Err on the side of caution and only keep jobs where 100% home office is almost certain. "
                "Return only the job titles, separated by a pipe symbol."
            )
        else:
            homeoffice_instruction = "Return only the job titles, separated by a pipe symbol."

        prompt_message = (
            f"Given the user's interests are in {interests_str}, and aiming to avoid positions such as {jobs_to_avoid_str}, "
            f"carefully review the following job listings, each separated by a pipe symbol. Each listing is formatted as 'Title: ... || Description: ...': {jobs_str}. "
            "Please list, separated by a pipe symbol, the job titles that align"
            "with the user's interests and do not fall into the categories to avoid. "
            f"{homeoffice_instruction}"
        )
        try:
            response = client.chat.completions.create(
                model="gpt-4-0125-preview",
                messages=[
                    {"role": "system",
                     "content": (
                        "You are a helpful assistant. Each job listing is separated by a pipe symbol and contains a title and description. "
                        "Your task is to identify job titles that align with the user's specified interests, and to avoid suggesting titles in the specified categories to avoid. "
                        "Use a pipe symbol to separate titles. Exclude titles that are clearly unrelated or fall into the avoidance categories. "
                        + (
                            "Additionally, ONLY include job titles where it is VERY LIKELY that the job can be performed 100% from home (full remote). "
                            "Be strict: Use all clues from the title and description, including synonyms and phrases like 'remote', 'work from anywhere', 'fully distributed', 'home office', '100% remote', 'completely remote', 'work from home', etc. "
                            "If there is any doubt, or if the job is only partially remote, hybrid, or the remote status is unclear, EXCLUDE the job. "
                            "Err on the side of caution and only keep jobs where 100% home office is almost certain. "
                            if homeoffice_required else ""
                        ) +
                        "Return only the job titles, separated by a pipe symbol."
                    )},
                    {"role": "user", "content": prompt_message}
                ]
            )

            filtered_titles = response.choices[0].message.content.strip().split('|')
            all_filtered_titles.extend(filtered_titles)
        except Exception as e:
            print(f"An error occurred while processing a batch: {e}")
            sys.exit()

    all_filtered_titles = [title.strip().rstrip('.') for title in all_filtered_titles if title.strip()]
    return all_filtered_titles
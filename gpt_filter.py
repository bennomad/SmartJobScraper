from openai import OpenAI
import os
from tqdm import tqdm
import sys
import pandas as pd

def filter_jobs_by_interest(openai_api_key, jobs, user_interests, jobs_to_avoid, homeoffice_required=False):
    """
    jobs: list of dicts, each with 'title' and 'description'
    homeoffice_required: if True, only keep jobs that are very likely 100% home office/remote
    """
    # Dump all jobs to CSV before filtering
    try:
        pd.DataFrame(jobs)[['title', 'description']].to_csv('all_jobs_input.csv', index=False)
        print(f"Dumped {len(jobs)} jobs to all_jobs_input.csv")
    except Exception as e:
        print(f"Failed to dump jobs to CSV: {e}")

    client = OpenAI(api_key=openai_api_key)

    print("Total jobs:", len(jobs))
    batch_size = 40  # Reduce batch size since descriptions are longer
    batches = [jobs[i:i + batch_size] for i in range(0, len(jobs), batch_size)]
    print(f"Splitting the total jobs into {len(batches)} API requests.")

    all_filtered_titles = []
    total_hallucinated_titles = 0

    def get_numbered_job_entries(jobs):
        return [f"[{i+1}] Title: {job['title']}" for i, job in enumerate(jobs)]

    def get_numbered_job_entries_with_desc(jobs):
        return [f"[{i+1}] Title: {job['title']} || Description: {job['description']}" for i, job in enumerate(jobs)]

    if homeoffice_required:
        # Step 1: Filter by title only, removing jobs to avoid
        print("Step 1: Filtering by job titles (removing jobs to avoid)...")
        title_batches = [jobs[i:i + batch_size] for i in range(0, len(jobs), batch_size)]
        filtered_jobs_step1 = []
        for batch in tqdm(title_batches, desc="Title Filtering Progress"):
            job_entries = get_numbered_job_entries(batch)
            jobs_to_avoid_str = " , ".join(jobs_to_avoid)
            prompt_message = (
                f"Given the user's interests are in {', '.join(user_interests)}, and aiming to avoid positions such as {jobs_to_avoid_str}, "
                f"review the following job titles, each with a unique number in brackets. Each entry is formatted as [number] Title: ...: {' '.join(job_entries)}. "
                "Return only the numbers of the job titles that do NOT fall into the categories to avoid, separated by commas. Do not return anything else."
            )
            try:
                response = client.chat.completions.create(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system",
                         "content": (
                            "You are a helpful assistant. Each job title is presented as a numbered entry in the format [number] Title: ... "
                            "Your task is to remove job titles that fall into the avoidance categories. "
                            "Return only the numbers of the job titles, separated by commas. Do not return anything else."
                        )},
                        {"role": "user", "content": prompt_message}
                    ]
                )
                filtered_numbers = [n.strip() for n in response.choices[0].message.content.strip().split(',') if n.strip().isdigit()]
                filtered_indices = [int(n)-1 for n in filtered_numbers if n.isdigit() and 0 < int(n) <= len(batch)]
                print(f"GPT returned {len(filtered_indices)} jobs for this batch")
                # Map back to jobs with these indices
                for idx in filtered_indices:
                    filtered_jobs_step1.append(batch[idx])
                # Hallucination: numbers out of range or not found
                hallucinated = len(filtered_numbers) - len(filtered_indices)
                if hallucinated > 0:
                    print(f"Total hallucinated job numbers in batch: {hallucinated}")
                    total_hallucinated_titles += hallucinated
            except Exception as e:
                print(f"An error occurred while processing a title batch: {e}")
                sys.exit()
        if total_hallucinated_titles > 0:
            print(f"Total hallucinated job numbers across all batches: {total_hallucinated_titles}")

        # Step 2: Filter by description for home office requirement, with reduced batch size
        print("Step 2: Filtering by description for 100% home office...")
        desc_batch_size = 10  # Smaller batch size for more accurate filtering
        desc_batches = [filtered_jobs_step1[i:i + desc_batch_size] for i in range(0, len(filtered_jobs_step1), desc_batch_size)]
        total_hallucinated_homeoffice = 0
        for batch in tqdm(desc_batches, desc="Home Office Filtering Progress"):
            job_entries = get_numbered_job_entries_with_desc(batch)
            prompt_message = (
                f"Review the following job listings, each with a unique number in brackets. Each entry is formatted as [number] Title: ... || Description: ...: {' '.join(job_entries)}. "
                "ONLY include job numbers where it is VERY LIKELY that the job can be performed 100% from home (full remote). "
                "Be strict: Use all clues from the title and description, including synonyms and phrases like 'remote', 'work from anywhere', 'fully distributed', 'home office', '100% remote', 'completely remote', 'work from home', etc. "
                "Return only the numbers of the job titles, separated by commas. Do not return anything else."
            )
            try:
                response = client.chat.completions.create(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system",
                         "content": (
                            "You are a helpful assistant. Each job listing is presented as a numbered entry in the format [number] Title: ... || Description: ... "
                            "Your task is to identify job titles that are VERY LIKELY 100% home office/remote. "
                            "Be strict: Use all clues from the title and description, including synonyms and phrases like 'remote', 'work from anywhere', 'fully distributed', 'home office', '100% remote', 'completely remote', 'work from home', etc. "
                            "Return only the numbers of the job titles, separated by commas. Do not return anything else."
                        )},
                        {"role": "user", "content": prompt_message}
                    ]
                )
                filtered_numbers = [n.strip() for n in response.choices[0].message.content.strip().split(',') if n.strip().isdigit()]
                filtered_indices = [int(n)-1 for n in filtered_numbers if n.isdigit() and 0 < int(n) <= len(batch)]
                # Hallucination: numbers out of range or not found
                hallucinated = len(filtered_numbers) - len(filtered_indices)
                if hallucinated > 0:
                    print(f"Home office filtering: Total hallucinated job numbers in batch: {hallucinated}")
                    total_hallucinated_homeoffice += hallucinated
                all_filtered_titles.extend([batch[idx]['title'] for idx in filtered_indices])
            except Exception as e:
                print(f"An error occurred while processing a description batch: {e}")
                sys.exit()
        if total_hallucinated_homeoffice > 0:
            print(f"Total hallucinated job numbers in home office filtering across all batches: {total_hallucinated_homeoffice}")
    else:
        print("Processing jobs (title + description)...")
        for batch in tqdm(batches, desc="Filtering Progress"):
            job_entries = get_numbered_job_entries_with_desc(batch)
            interests_str = ", ".join(user_interests)
            jobs_to_avoid_str = " , ".join(jobs_to_avoid)
            homeoffice_instruction = "Return only the numbers of the job titles, separated by commas. Do not return anything else."
            prompt_message = (
                f"Given the user's interests are in {interests_str}, and aiming to avoid positions such as {jobs_to_avoid_str}, "
                f"carefully review the following job listings, each with a unique number in brackets. Each entry is formatted as [number] Title: ... || Description: ...: {' '.join(job_entries)}. "
                "Please list, separated by commas, the numbers of the job titles that align with the user's interests and do not fall into the categories to avoid. "
                f"{homeoffice_instruction}"
            )
            try:
                response = client.chat.completions.create(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system",
                         "content": (
                            "You are a helpful assistant. Each job listing is presented as a numbered entry in the format [number] Title: ... || Description: ... "
                            "Your task is to identify job titles that align with the user's specified interests, and to avoid suggesting titles in the specified categories to avoid. "
                            "Return only the numbers of the job titles, separated by commas. Do not return anything else."
                        )},
                        {"role": "user", "content": prompt_message}
                    ]
                )
                filtered_numbers = [n.strip() for n in response.choices[0].message.content.strip().split(',') if n.strip().isdigit()]
                filtered_indices = [int(n)-1 for n in filtered_numbers if n.isdigit() and 0 < int(n) <= len(batch)]
                all_filtered_titles.extend([batch[idx]['title'] for idx in filtered_indices])
            except Exception as e:
                print(f"An error occurred while processing a batch: {e}")
                sys.exit()
    all_filtered_titles = [title.strip().rstrip('.') for title in all_filtered_titles if title.strip()]
    return all_filtered_titles
from openai import OpenAI
import os
from tqdm import tqdm
import sys
import pandas as pd

def filter_jobs_by_interest(openai_api_key, jobs, user_interests, jobs_to_avoid, homeoffice_required=False, jobs_to_include=None, experience_level=None):
    """
    jobs: list of dicts, each with 'title' and 'description' and optionally 'analyzed'
    homeoffice_required: if True, only keep jobs that are very likely 100% home office/remote
    jobs_to_include: list of terms that should be preferred in job filtering
    experience_level: string, e.g. 'junior', 'mid', 'senior', 'any'
    
    Returns a tuple with three lists:
    1. step1_filtered_titles - after basic filtering
    2. step2_filtered_titles - after homeoffice filtering (if required)
    3. step3_filtered_titles - after user interests filtering
    Also, all jobs that are processed (not skipped) will have 'analyzed' set to 1.
    """
    if jobs_to_include is None:
        jobs_to_include = []

    # Skip jobs that have already been analyzed
    jobs = [job for job in jobs if not job.get('analyzed', 0)]

    # Manual filter: if experience_level is 'junior', drop all jobs with 'senior ' in the title
    if experience_level and experience_level.lower() == 'junior':
        before_count = len(jobs)
        jobs = [job for job in jobs if 'senior ' not in job['title'].lower()]
        after_count = len(jobs)
        print(f"Manual filter: removed {before_count - after_count} jobs containing 'senior ' in the title for junior level.")
        
    client = OpenAI(api_key=openai_api_key)

    print("Total jobs:", len(jobs))
    batch_size = 40  
    batches = [jobs[i:i + batch_size] for i in range(0, len(jobs), batch_size)]
    print(f"Splitting the total jobs into {len(batches)} API requests.")

    step1_filtered_titles = []
    step2_filtered_titles = []
    step3_filtered_titles = []

    def get_numbered_job_entries(jobs):
        return [f"[{i+1}] Title: {job['title']}" for i, job in enumerate(jobs)]

    def get_numbered_job_entries_with_desc(jobs):
        return [f"[{i+1}] Title: {job['title']} || Description: {job['description']}" for i, job in enumerate(jobs)]

    # Track if prompt has been dumped
    prompt1_dumped = False
    prompt2_dumped = False
    prompt3_dumped = False

    # Step 1: Filter by title only, removing jobs to avoid
    print("Step 1: Filtering by job titles (removing jobs to avoid)...")
    title_batches = [jobs[i:i + batch_size] for i in range(0, len(jobs), batch_size)]
    filtered_jobs_step1 = []
    for batch_idx, batch in enumerate(tqdm(title_batches, desc="Title Filtering Progress")):
        job_entries = get_numbered_job_entries(batch)
        jobs_to_avoid_str = " , ".join(jobs_to_avoid)
        include_terms_str = " , ".join(jobs_to_include) if jobs_to_include else ""
        
        include_instruction = ""
        if jobs_to_include:
            include_instruction = f" Give preference to jobs with these terms: {include_terms_str},"
        
        # Step 1: Basic filtering prompt
        prompt_message = (
            f"Your task is to identify job titles that do NOT contain terms such as {jobs_to_avoid_str}. "
            "Review the following job titles, each with a unique number in brackets. "
            f"Each entry is formatted as [number] Title: ...: {' '.join(job_entries)}. "
            "Return only the numbers of the job titles, separated by commas. Do not return anything else."
        )
        # Dump first prompt message of step 1
        if not prompt1_dumped:
            with open('prompt_step1.txt', 'w', encoding='utf-8') as f:
                f.write(prompt_message)
            prompt1_dumped = True
        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system",
                     "content": (
                        "You are a helpful assistant. Your task is to remove job titles that fall into the avoidance categories. "
                        "Each job title is presented as a numbered entry in the format [number] Title: ... "
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
                job = batch[idx]
                job['analyzed'] = 1  # Tag as analyzed
                filtered_jobs_step1.append(job)
        except Exception as e:
            print(f"An error occurred while processing a title batch: {e}")
            sys.exit()

    step1_filtered_titles = [job['title'].strip().rstrip('.') for job in filtered_jobs_step1 if job['title'].strip()]
    print(f"Step 1 results: {len(step1_filtered_titles)} jobs passed the title filtering.")
    
    # If homeoffice is required, proceed with step 2, otherwise skip to step 3
    if homeoffice_required:
        # Step 2: Filter by description for home office requirement, with reduced batch size
        print("Step 2: Filtering by description for 100% home office...")
        desc_batch_size = 10  # Smaller batch size for more accurate filtering
        desc_batches = [filtered_jobs_step1[i:i + desc_batch_size] for i in range(0, len(filtered_jobs_step1), desc_batch_size)]
        filtered_jobs_step2 = []
        for batch_idx, batch in enumerate(tqdm(desc_batches, desc="Home Office Filtering Progress")):
            job_entries = get_numbered_job_entries_with_desc(batch)
            # Step 2: Home office filtering prompt
            prompt_message = (
                "Your task is to identify job listings that are VERY LIKELY to be 100% remote/home office positions. "
                "Be extremely strict: Only select jobs where it is clearly stated that the position is fully remote, 100% home office, or similar. "
                "Exclude jobs where remote or home office is not mentioned, or where only vague or partial options are given (such as 'homeoffice möglichkeit', 'option for home office', '1 day a week home office', or similar phrases). "
                "Look for clear indicators like 'remote', 'work from anywhere', 'fully distributed', 'home office', '100% remote', 'completely remote', 'work from home', etc. "
                "Review the following job listings, each with a unique number in brackets. "
                f"Each entry is formatted as [number] Title: ... || Description: ...: {' '.join(job_entries)}. "
                "Return only the numbers of the job titles, separated by commas. Do not return anything else."
            )
            # Dump first prompt message of step 2
            if not prompt2_dumped:
                with open('prompt_step2.txt', 'w', encoding='utf-8') as f:
                    f.write(prompt_message)
                prompt2_dumped = True
            try:
                response = client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=[
                        {"role": "system",
                         "content": (
                            "You are a helpful assistant. Your task is to identify job titles that are VERY LIKELY 100% home office/remote. "
                            "Be extremely strict: Only select jobs where it is clearly stated that the position is fully remote, 100% home office, or similar. "
                            "Exclude jobs where remote or home office is not mentioned, or where only vague or partial options are given (such as 'homeoffice möglichkeit', 'option for home office', '1 day a week home office', or similar phrases). "
                            "Be strict in your evaluation of remote work indicators. "
                            "Each job listing is presented as a numbered entry in the format [number] Title: ... || Description: ... "
                            "Return only the numbers of the job titles, separated by commas. Do not return anything else."
                        )},
                        {"role": "user", "content": prompt_message}
                    ]
                )
                filtered_numbers = [n.strip() for n in response.choices[0].message.content.strip().split(',') if n.strip().isdigit()]
                filtered_indices = [int(n)-1 for n in filtered_numbers if n.isdigit() and 0 < int(n) <= len(batch)]
                for idx in filtered_indices:
                    job = batch[idx]
                    job['analyzed'] = 1  # Tag as analyzed
                    filtered_jobs_step2.append(job)
            except Exception as e:
                print(f"An error occurred while processing a description batch: {e}")
                sys.exit()
        
        step2_filtered_titles = [job['title'].strip().rstrip('.') for job in filtered_jobs_step2 if job['title'].strip()]
        print(f"Step 2 results: {len(step2_filtered_titles)} jobs passed the home office filtering.")
        
        # Prepare jobs for step 3
        jobs_to_filter_step3 = filtered_jobs_step2
    else:
        # Skip step 2, use step 1 results for step 3
        step2_filtered_titles = step1_filtered_titles
        jobs_to_filter_step3 = filtered_jobs_step1
        print("Skipping Step 2 (home office filtering) as it's not required.")
    
    # Step 3: Filter by user interests
    print("Step 3: Filtering by user interests...")
    interest_batch_size = 10  # Smaller batch size for more detailed filtering
    interest_batches = [jobs_to_filter_step3[i:i + interest_batch_size] for i in range(0, len(jobs_to_filter_step3), interest_batch_size)]
    filtered_jobs_step3 = []
    for batch_idx, batch in enumerate(tqdm(interest_batches, desc="Interest Filtering Progress")):
        job_entries = get_numbered_job_entries_with_desc(batch)
        interests_str = ", ".join(user_interests)
        custom_exclude_terms_str = " , ".join(jobs_to_avoid)
        
        # Step 3: Interest and exclusion filtering prompt
        prompt_message = (
            f"Your task is to identify job listings that align with the user's interests ({interests_str}) "
            f"and do NOT match any of the following avoidance instructions or requirements: {custom_exclude_terms_str}. "
            "This includes jobs whose title or description suggests any of these requirements, even if the exact wording is not used. "
            "Review the following job listings, each with a unique number in brackets. "
            f"Each entry is formatted as [number] Title: ... || Description: ...: {' '.join(job_entries)}. "
            "Return only the numbers of the job titles, separated by commas. Do not return anything else."
        )
        # Dump first prompt message of step 3
        if not prompt3_dumped:
            with open('prompt_step3.txt', 'w', encoding='utf-8') as f:
                f.write(prompt_message)
            prompt3_dumped = True
        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system",
                     "content": (
                        "You are a helpful assistant. Your task is to identify job titles that align with the user's specified interests "
                        "and do not match any of the user's avoidance instructions or requirements (not just keywords, but also described requirements or conditions). "
                        "Each job listing is presented as a numbered entry in the format [number] Title: ... || Description: ... "
                        "Return only the numbers of the job titles, separated by commas. Do not return anything else."
                    )},
                    {"role": "user", "content": prompt_message}
                ]
            )
            filtered_numbers = [n.strip() for n in response.choices[0].message.content.strip().split(',') if n.strip().isdigit()]
            filtered_indices = [int(n)-1 for n in filtered_numbers if n.isdigit() and 0 < int(n) <= len(batch)]
            for idx in filtered_indices:
                job = batch[idx]
                job['analyzed'] = 1  # Tag as analyzed
                filtered_jobs_step3.append(job)
        except Exception as e:
            print(f"An error occurred while processing an interest batch: {e}")
            sys.exit()
    
    step3_filtered_titles = [job['title'].strip().rstrip('.') for job in filtered_jobs_step3 if job['title'].strip()]
    print(f"Step 3 results: {len(step3_filtered_titles)} jobs passed the interest filtering.")
    
    return (step1_filtered_titles, step2_filtered_titles, step3_filtered_titles)
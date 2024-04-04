from openai import OpenAI
import os
from tqdm import tqdm
import sys

def filter_job_titles_by_interest(openai_api_key, job_titles, user_interests, jobs_to_avoid):

    client = OpenAI(api_key=openai_api_key)

    print("Total jobs:", len(job_titles))
    # Splitting job titles into batches of a manageable size
    batch_size = 100  # Example size, adjust based on experimentation
    batches = [job_titles[i:i + batch_size] for i in range(0, len(job_titles), batch_size)]
    print(f"Splitting the total jobs into {len(batches)} API requests.")

    all_filtered_titles = []

    print("Processing job titles...")
    for batch in tqdm(batches, desc="Filtering Progress"):
        job_titles_str = " | ".join(batch)
        interests_str = ", ".join(user_interests)
        # Assuming jobs_to_avoid is a list of titles/keywords to avoid
        jobs_to_avoid_str = " , ".join(jobs_to_avoid)

        prompt_message = (
            f"Given the user's interests are in {interests_str}, and aiming to avoid positions such as {jobs_to_avoid_str}, "
            f"carefully review the following job titles, each separated by a pipe symbol: {job_titles_str}. "
            "Please list, separated by a pipe symbol, the job titles that align, even remotely, "
            "with the user's interests and do not fall into the categories to avoid. "
            "Exclude titles only if they are clearly unrelated or are listed in the categories to avoid."
        )
        try:
            response = client.chat.completions.create(
                model="gpt-4-0125-preview",
                messages=[
                    {"role": "system",
                     "content": "You are a helpful assistant. Each job title is separated by a pipe symbol. Your task is to identify job titles that align with the user's specified interests, no matter how tangentially, and to avoid suggesting titles in the specified categories to avoid. Use a pipe symbol to separate titles. Exclude titles that are clearly unrelated or fall into the avoidance categories."},
                    {"role": "user", "content": prompt_message}
                ]
            )

            filtered_titles = response.choices[0].message.content.strip().split('|')
            all_filtered_titles.extend(filtered_titles)
        except Exception as e:
            print(f"An error occurred while processing a batch: {e}")
            sys.exit()

    # Remove any empty strings that might have slipped through and remove trailing periods
    all_filtered_titles = [title.strip().rstrip('.') for title in all_filtered_titles if title.strip()]
    return all_filtered_titles
#! /usr/bin/env python
import asyncio
from tqdm.asyncio import tqdm_asyncio
import os
from openai import AsyncOpenAI
import json
import datasets
from natsort import natsorted
import ast

async_client = AsyncOpenAI(
    base_url="https://api.together.xyz/v1",
    api_key=os.environ["TOGETHER_API_KEY"]
)


class Config:
    def __init__(self):
        # Model parameters
        # self.model_name = "deepseek-ai/DeepSeek-R1"
        self.model_name = "mistralai/Mistral-7B-Instruct-v0.2"
        # self.temperature = 0.6
        # self.top_p = 0.95
        # self.max_tokens = 32768
        
        # Data parameters
        # self.dataset_path = "rasdani/swe-fixer-70k"
        self.dataset_path = "rasdani/ifeval-genesys-debug"
        self.max_samples = 48
        self.batch_size = 1
        self.num_responses_per_question = 1
        
        # Output parameters
        self.out_file_prefix = "out"
        self.path_output = "output/ifeval_48"
        self.sample_per_file = 5

def save_batch_results(results, file_path):
    """Save batch results to a JSONL file."""
    # Ensure output directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Save results to file
    with open(file_path, 'w') as f:
        for result in results:
            # Convert Python objects to strings for serialization
            result_copy = result.copy()
            f.write(json.dumps(result_copy) + '\n')
    
    return file_path

async def async_gather_generate_responses(async_client, dataset, config):
    """Generate responses for examples in the dataset using async/await pattern."""
    # Empty the output directory if it exists, or create it if not present
    if os.path.exists(config.path_output):
        for file in os.listdir(config.path_output):
            os.remove(os.path.join(config.path_output, file))
    else:
        os.makedirs(config.path_output)
    all_results = []
    total_samples = 0
    # sampling_params = {
    #     "max_tokens": config.max_tokens
    # }
    
    async def process_example(example):
        """Process a single example asynchronously."""
        print(f"Processing example {example['problem_id']}")
        messages = [
            {"role": "user", "content": example["prompt"]}
        ]
        
        # Generate response using the OpenAI API
        try:
            response = await async_client.chat.completions.create(
                model=config.model_name,
                messages=messages,
                # max_tokens=sampling_params["max_tokens"]
            )
            llm_response = response.choices[0].message.content
        except Exception as e:
            print(f"Error processing example {example['problem_id']}: {e}")
            llm_response = "Error: " + str(e)
        
        # Extract the response text
        
        print(f"Example {example['problem_id']} completed")
        metadata = example.get("metadata", "{}")
        # metadata = ast.literal_eval(metadata)
        # metadata["model"] = config.model_name
        # metadata["prompt"] = example["prompt"]
        
        example["metadata"] = metadata
        example["llm_response"] = llm_response
        # return {
        #     "problem_id": example["problem_id"],  # Used for result indexing
        #     "source": example.get("source", ""),  # Used by some verifiers (e.g., ReasoningGymVerifier)
        #     "task_type": example["task_type"],    # Used to select the appropriate verifier
        #     "verification_info": example.get("verification_info", {}),  # Required for verification
        #     "metadata": metadata,  # Required for verification
        #     "llm_response": llm_response,  # The actual response to verify
        # }
        return example

    # Process in batches according to config
    for i in range(0, len(dataset), config.batch_size):
        batch = dataset.select(range(i, i+config.batch_size))
        # Create tasks for all examples in the batch
        tasks = [process_example(example) for example in batch]
        
        batch_no = i//config.batch_size + 1
        # Use tqdm to show progress for the batch
        batch_results = await tqdm_asyncio.gather(*tasks, desc=f"Processing batch {batch_no} of {len(dataset)//config.batch_size}")
        all_results.extend(batch_results)
        total_samples += len(batch_results)
        
        # Save batch results when we reach the sample_per_file threshold
        if len(all_results) >= config.sample_per_file:
            file_name = f"{config.out_file_prefix}_{batch_no:04d}.jsonl"
            file_path = os.path.join(config.path_output, file_name)
            save_batch_results(all_results, file_path)
            print(f"✨ Saved {len(all_results)} samples to {file_path}")
            all_results = []
    
    # Save any remaining results
    if len(all_results) > 0:
        file_name = f"{config.out_file_prefix}_0000.jsonl"
        file_path = os.path.join(config.path_output, file_name)
        save_batch_results(all_results, file_path)
        print(f"✨ Saved {len(all_results)} samples to {file_path}")
    
    print(f"✨ Generation complete! Total samples: {total_samples}")
    return file_path

def merge_results(output_dir):
    # Concatenate all JSONLs in output directory into a single dataset
    all_files = natsorted([os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith('.jsonl')])
    verified_ds = datasets.load_dataset('json', data_files=all_files, split='train')
    # Dump all examples to a single JSONL file
    output_path = os.path.join(output_dir, "output.jsonl")
    with open(output_path, 'w') as f:
        for example in verified_ds:
            f.write(json.dumps(example) + '\n')
    print(f"✨ Saved {len(verified_ds)} examples to {output_path}")

if __name__ == "__main__":
    config = Config()

    ds = datasets.load_dataset(config.dataset_path, split="train").shuffle(seed=42).select(range(config.max_samples))
    print(f"Loaded {len(ds)} examples from {config.dataset_path}")

    asyncio.run(async_gather_generate_responses(async_client, ds, config))
    merge_results(config.path_output)

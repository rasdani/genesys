import ast
import json
import re
import subprocess
import tempfile
from pathlib import Path
from datasets import load_dataset
from tqdm.auto import tqdm


def remove_line_numbers(content):
    """Remove line numbers from the beginning of each line."""
    return re.sub(r"^\d+\s", "", content, flags=re.MULTILINE)


def apply_patches(files, patches):
    """Apply patches to files and return patched workspace."""
    # Create workspace from original files
    workspace = {f["file"]: remove_line_numbers(f["file content"]) for f in files}
    
    # Apply each patch
    for patch in patches:
        file_path = patch["file"]
        old_snippet = remove_line_numbers(patch["code snippet to be modified"]).strip()
        new_snippet = patch["edited code snippet"].strip()
        
        if file_path in workspace:
            if old_snippet:
                workspace[file_path] = workspace[file_path].replace(old_snippet, new_snippet)
            else:
                workspace[file_path] = new_snippet
    
    return workspace


def generate_git_diff(before, after, file_path):
    """Generate diff using git diff command."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write temporary files
        before_file = Path(tmpdir) / "a" / file_path
        after_file = Path(tmpdir) / "b" / file_path
        
        before_file.parent.mkdir(parents=True, exist_ok=True)
        after_file.parent.mkdir(parents=True, exist_ok=True)
        
        before_file.write_text(before)
        after_file.write_text(after)
        
        # Run git diff
        result = subprocess.run(
            ["git", "diff", "--no-index", "--no-prefix", str(before_file), str(after_file)],
            capture_output=True, text=True
        )
        
        return result.stdout


def generate_workspace_git_diff(original_workspace, modified_workspace):
    """Generate a unified git diff for the entire workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create directory structures
        before_dir = Path(tmpdir) / "a"
        after_dir = Path(tmpdir) / "b"
        
        # Write all files for both workspaces
        all_files = set(original_workspace.keys()) | set(modified_workspace.keys())
        
        for file_path in all_files:
            # Write original file
            before_file = before_dir / file_path
            before_file.parent.mkdir(parents=True, exist_ok=True)
            before_content = original_workspace.get(file_path, "")
            before_file.write_text(before_content)
            
            # Write modified file
            after_file = after_dir / file_path
            after_file.parent.mkdir(parents=True, exist_ok=True)
            after_content = modified_workspace.get(file_path, "")
            after_file.write_text(after_content)
        
        # Run git diff on entire directories
        result = subprocess.run(
            ["git", "diff", "--no-index", "--src-prefix=a/", "--dst-prefix=b/", str(before_dir), str(after_dir)],
            capture_output=True, text=True
        )
        
        # Remove index lines and clean tmp paths using regex
        diff_output = result.stdout
        diff_output = re.sub(r'diff --git.*?\nindex [a-f0-9]+\.\.[a-f0-9]+ \d+\n', lambda m: m.group(0).split('\nindex')[0] + '\n', diff_output, flags=re.DOTALL)
        diff_output = re.sub(re.escape(str(tmpdir)) + r'/[ab]', '', diff_output)
        
        return diff_output


def preprocess_dataset(dataset):
    """Preprocess SWE-Fixer dataset examples."""
    
    preprocessed = []
    
    for example in tqdm(dataset, desc="Processing examples"):
        try:
            # Extract data
            verification_info = ast.literal_eval(example["verification_info"])
            original_files = verification_info["input"]["files to be modified"]
            golden_patches = verification_info["output"]["edited code"]
            
            # Apply patches
            original_workspace = apply_patches(original_files, [])
            golden_workspace = apply_patches(original_files, golden_patches)
            
            # Generate workspace-wide diff
            workspace_diff = generate_workspace_git_diff(original_workspace, golden_workspace)
            
            # Store preprocessed data
            preprocessed.append({
                "problem_id": example["problem_id"],
                "original_files": original_workspace,
                "golden_files": golden_workspace,
                "golden_diff": workspace_diff,
                "metadata": example.get("metadata", {})
            })
            
        except Exception as e:
            print(f"Error processing {example.get('problem_id', 'unknown')}: {e}")
    
    return preprocessed


def save_preprocessed_data(preprocessed_data, output_path="preprocessed_swe_fixer.jsonl"):
    """Save preprocessed data to JSONL file."""
    with open(output_path, "w") as f:
        for item in preprocessed_data:
            f.write(json.dumps(item) + "\n")
    print(f"Saved {len(preprocessed_data)} examples to {output_path}")


def load_preprocessed_data(file_path="preprocessed_swe_fixer.jsonl"):
    """Load preprocessed data from JSONL file."""
    data = []
    with open(file_path, "r") as f:
        for line in f:
            data.append(json.loads(line))
    return data


# Example usage in notebook:
if __name__ == "__main__":
    # Load dataset
    dataset = load_dataset("rasdani/swe-fixer-70k", split="train")
    dataset = dataset.select(range(10))
    
    # Preprocess (use limit for testing)
    preprocessed = preprocess_dataset(dataset)
    
    # Save to file
    save_preprocessed_data(preprocessed)
    
    # Example: inspect first example
    if preprocessed:
        example = preprocessed[0]
        print(f"Problem ID: {example['problem_id']}")
        print(f"Files modified: {list(example['golden_files'].keys())}")
        print(f"\nWorkspace diff:")
        print(example['golden_diff'][:500] + "...")
    breakpoint()
import ast
import json
import re
import subprocess
import tempfile
from pathlib import Path
from datasets import load_dataset
from tqdm.auto import tqdm
from typing import Optional, Dict
import requests
import difflib


REMOVE_INDEX_REGEX = re.compile(r'diff --git.*?\nindex [a-f0-9]+\.\.[a-f0-9]+ \d+\n', re.DOTALL)

def normalize_diff(diff, tmp_dir=None):
    # Remove index lines completely (they appear as separate lines)
    diff = re.sub(r'^index [a-f0-9]+\.\.[a-f0-9]+ \d+\n', '', diff, flags=re.MULTILINE)
    if tmp_dir:
        diff = re.sub(re.escape(str(tmp_dir)) + r'/[ab]', '', diff)
    return diff

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
        diff_output = normalize_diff(diff_output, tmpdir)
        
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
            # preprocessed.append({
            #     "problem_id": example["problem_id"],
            #     "original_files": original_workspace,
            #     "golden_files": golden_workspace,
            #     "golden_diff": workspace_diff,
            #     "metadata": example.get("metadata", {})
            # })
            preprocessed.append({
                **example,
                "original_files": original_workspace,
                "golden_files": golden_workspace,
                "golden_diff": workspace_diff,
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

def extract_pr_info(in_source_id: str) -> Optional[Dict[str, str]]:
    """Extract GitHub PR information from in_source_id."""
    if not in_source_id:
        return None
    
    # Handle format like "python-gitlab__python-gitlab-642"
    # This maps to https://github.com/python-gitlab/python-gitlab/pull/642
    if "__" in in_source_id:
        parts = in_source_id.split("__")
        if len(parts) == 2:
            owner = parts[0]
            repo_pr = parts[1]
            
            # Extract repo name and PR number
            # Format: repo-name-PRNUMBER
            match = re.match(r"(.+)-(\d+)$", repo_pr)
            if match:
                repo_name = match.group(1)
                pr_number = match.group(2)
                
                repo = f"{owner}/{repo_name}"
                pr_url = f"https://github.com/{repo}/pull/{pr_number}"
                
                return {
                    "repo": repo,
                    "pr_number": pr_number,
                    "pr_url": pr_url
                }
    
    return None


def fetch_pr_diff(repo: str, pr_number: str, github_token: Optional[str] = None) -> Optional[str]:
    """Fetch the actual diff from a GitHub PR."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    
    headers = {"Accept": "application/vnd.github.v3.diff"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error fetching PR diff for {repo}#{pr_number}: {e}")
        return None



def extract_files_from_diff(diff: str) -> set:
    """Extract file paths from a git diff."""
    files = set()
    for line in diff.split('\n'):
        if line.startswith('diff --git'):
            # Extract file path from "diff --git a/path b/path"
            parts = line.split()
            if len(parts) >= 4:
                # Take the path after "a/" 
                file_path = parts[2]
                if file_path.startswith('a/'):
                    file_path = file_path[2:]
                files.add(file_path)
    return files


def filter_diff_by_files(diff: str, allowed_files: set) -> str:
    """Filter a git diff to only include changes for specific files."""
    if not allowed_files:
        return diff
    
    lines = diff.split('\n')
    filtered_lines = []
    include_section = False
    
    for line in lines:
        if line.startswith('diff --git'):
            # Check if this file should be included
            parts = line.split()
            if len(parts) >= 4:
                file_path = parts[2]
                if file_path.startswith('a/'):
                    file_path = file_path[2:]
                include_section = file_path in allowed_files
            else:
                include_section = False
        
        if include_section:
            filtered_lines.append(line)
    
    return '\n'.join(filtered_lines)


def create_diff_comparison(golden_diff: str, github_diff: str) -> str:
    """Create a detailed diff comparison between golden and github diffs."""
    golden_lines = golden_diff.splitlines(keepends=True)
    github_lines = github_diff.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        golden_lines,
        github_lines,
        fromfile="golden_diff",
        tofile="github_diff",
        lineterm=""
    )
    
    return ''.join(diff)

def compare_diffs(golden_diff: str, github_diff: str) -> float:
    """Compare two diffs and return a similarity score."""
    # Extract files from golden diff and filter github diff to only include those files
    golden_files = extract_files_from_diff(golden_diff)
    
    github_diff_filtered = filter_diff_by_files(github_diff, golden_files)
    
    # Normalize both diffs to remove index lines and clean up formatting
    golden_diff_normalized = normalize_diff(golden_diff)
    github_diff_normalized = normalize_diff(github_diff_filtered)
    
    # Show the diff between the two patches
    diff_comparison = create_diff_comparison(golden_diff_normalized, github_diff_normalized)
    print(f"Diff between golden and github patches:")
    print(diff_comparison)
    
    if golden_diff_normalized == github_diff_normalized:
        return 1.0
    
    # Calculate line-based similarity
    golden_lines = set(golden_diff_normalized.split('\n'))
    github_lines = set(github_diff_normalized.split('\n'))
    
    if not golden_lines and not github_lines:
        return 1.0
    if not golden_lines or not github_lines:
        return 0.0
    
    intersection = len(golden_lines & github_lines)
    union = len(golden_lines | github_lines)
    
    return intersection / union if union > 0 else 0.0

def validate_against_pr(example: dict, golden_diff: str, 
                       github_token: Optional[str] = None) -> dict:
    """Validate golden patches against actual GitHub PR."""
    pr_info = extract_pr_info(example.get("in_source_id"))
    if not pr_info:
        return {"status": "no_pr_info"}
    
    # Fetch actual PR diff
    pr_diff_text = fetch_pr_diff(pr_info["repo"], pr_info["pr_number"], github_token)
    if not pr_diff_text:
        return {"status": "fetch_failed", "pr_info": pr_info}
    
    
    # Compare whole unified diff
    score = compare_diffs(golden_diff, pr_diff_text)
    print(score)
    if score == 1.0:
        return {"status": "validated", "pr_info": pr_info, "score": score}
    else:
        breakpoint()
    
    # Check for files in PR but not in golden
    extra_files = set(pr_diff_text.split('\n')) - set(golden_diff.split('\n'))
    
    return {
        "status": "validated",
        "pr_info": pr_info,
        "avg_similarity": score,
        "extra_files_in_pr": list(extra_files),
        "perfect_match": score == 1.0 and not extra_files
    }

# Example usage in notebook:
if __name__ == "__main__":
    # Load dataset
    dataset = load_dataset("rasdani/swe-fixer-70k", split="train")
    dataset = dataset.select([1])
    
    # Preprocess (use limit for testing)
    preprocessed = preprocess_dataset(dataset)
    
    # Save to file
    save_preprocessed_data(preprocessed)
    
    # Example: inspect first example
    if preprocessed:
        example = preprocessed[0]
        # print(f"Problem ID: {example['problem_id']}")
        # print(f"Files modified: {list(example['golden_files'].keys())}")
        # print(f"\nWorkspace diff:")
        # print(example['golden_diff'][:500] + "...")
    
    for example in preprocessed:
        validate_against_pr(example, example['golden_diff'])
    breakpoint()
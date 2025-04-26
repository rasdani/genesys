### adapted from https://github.com/InternLM/SWE-Fixer/blob/main/evaluation/code_edit.py
import json
import re
import ast
import argparse
import cydifflib
from genesys.schemas import Response
from genesys.verifiers.base_verifier import BaseVerifier


def parse_json_codeblock_from_model_output(markdown_str):
    # Get everything after </think>, if it exists
    match = re.search(r"</think>(.*?)$", markdown_str, re.DOTALL)
    answer_str = match.group(1).strip() if match else markdown_str.strip()
    # Extract everything between ```json and ``` markers
    match = re.search(r"```json\s*(.*?)\s*```", answer_str, re.DOTALL)
    if match:
        return match.group(1).strip()
    else:
        return answer_str.strip()


def remove_line_numbers(content):
    # Remove line numbers from the file content
    return re.sub(r"^\d+\s", "", content, flags=re.MULTILINE)

def remove_empty_lines(code):
    lines = code.splitlines()
    filtered_lines = [line for line in lines if line.strip() != ""]
    return "\n".join(filtered_lines)


def check_syntax(code):
    if not code.strip():
        return False
    try:
        ast.parse(code)
    except SyntaxError:
        return False
    return True


def differs_by_just_empty_lines(code, prev_code):
    normalized_code1 = remove_empty_lines(code)
    normalized_code2 = remove_empty_lines(prev_code)
    return normalized_code1 == normalized_code2

def color_print_diff(code, prev_code):
    # Create a differ object
    differ = cydifflib.Differ()
    
    # Split both codes into lines
    code_lines = code.splitlines()
    prev_code_lines = prev_code.splitlines()
    
    # Get the diff
    diff = list(differ.compare(prev_code_lines, code_lines))
    
    # Print the diff with colors
    for line in diff:
        if line.startswith('+'):
            print('\033[92m' + line + '\033[0m')  # Green for additions
        elif line.startswith('-'):
            print('\033[91m' + line + '\033[0m')  # Red for deletions
        elif line.startswith('?'):
            continue  # Skip the hints
        else:
            print(line)  # Normal color for unchanged lines


def apply_patches(files_to_modify, patches):
    """
    Apply a list of code-edit patches to an iterable of files and return the
    fully-patched workspace.

    Args:
        files_to_modify (list[dict]): items from verification_info["input"]["files to be modified"]
        patches (list[dict]): items structured like verification_info["output"]["edited code"]
                              or the model's JSON output.

    Returns
    -------
    dict[str, str]
        file-path -> patched file content
    """
    # 1. start with the unmodified text for every file
    file_map = {f["file"]: remove_line_numbers(f["file content"])
                for f in files_to_modify}

    # 2. iteratively apply every patch, mutating the working copy
    for patch in patches:
        file_path = patch["file"]
        snippet_old = remove_line_numbers(
            patch["code snippet to be modified"]
        ).rstrip()
        snippet_new = patch["edited code snippet"]

        current = file_map.get(file_path, "")
        if snippet_old and snippet_old in current:
            current = current.replace(snippet_old, snippet_new)
        elif current == "":           # brand-new file
            current = snippet_new
        file_map[file_path] = current

    return file_map


class SweFixerVerifier(BaseVerifier):
    """
    Verifier for the SWE-Fixer dataset.
    https://github.com/InternLM/SWE-Fixer
    """

    def evaluate_task_code_editing(self, verification_info, json_output):
        try:
            model_patches = json.loads(json_output)
        except Exception as e:
            return dict(score=0.0, verification_result_info={
                "failure_reason": f"Error in parsing JSON output: {e}"
            })

        try:
            original_files = verification_info["input"]["files to be modified"]
            golden_patches = verification_info["output"]["edited code"]

            expected_ws  = apply_patches(original_files, golden_patches)
            predicted_ws = apply_patches(original_files, model_patches)
            # predicted_ws = apply_patches(original_files, golden_patches)

            

            scores = []
            for path in expected_ws:
                expected_code  = expected_ws[path]
                predicted_code = predicted_ws.get(path, "")

                if predicted_code == expected_code or differs_by_just_empty_lines(predicted_code, expected_code):
                    scores.append(1.0)
                    continue


                syntax_ok = check_syntax(predicted_code)
                if not syntax_ok:
                    # color_print_diff(predicted_code, expected_code)
                    return dict(score=0.0, verification_result_info={
                        "failure_reason": "Syntax error"
                    })
                
                score = cydifflib.SequenceMatcher(
                    None,
                    a=predicted_code,
                    b=expected_code,
                    autojunk=False,
                ).ratio()
                scores.append(score)
                

            return dict(score=sum(scores) / len(scores), verification_result_info=dict())


        except Exception as e:
            return dict(
                score=0,
                verification_result_info={
                    "failure_reason": f"Error in evaluating task code editing: {e}"
                },
            )

    def verify(self, result: Response):
        """
        Evaluates the code patches by comparing the model's patches against golden patches.

        The score is either 0 or 1, representing whether the patches are correct.
        """

        verification_info = result["verification_info"]
        json_output = parse_json_codeblock_from_model_output(result["llm_response"])

        return self.evaluate_task_code_editing(verification_info, json_output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Verify SWE-Fixer patches')
    parser.add_argument('--file', type=str, required=True, help='Path to the input file containing patches to verify')
    args = parser.parse_args()

    to_verify = []
    with open(args.file, "r") as f:
        for line in f:
            d = json.loads(line)
            d["verification_info"] = ast.literal_eval(d["verification_info"])
            d["metadata"] = ast.literal_eval(d["metadata"])
            to_verify.append(d)
    
    verifier = SweFixerVerifier()
    for item in to_verify:
        result = verifier.verify(item)
        print(result)

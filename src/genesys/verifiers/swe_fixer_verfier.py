### adapted from https://github.com/InternLM/SWE-Fixer/blob/main/evaluation/code_edit.py
import json
import os
import re
import ast
import argparse

from genesys.schemas import Response
from genesys.verifiers.base_verifier import BaseVerifier


def parse_json_codeblock_from_reasoning_model_output(markdown_str):
    _, answer_str = markdown_str.split("</think>")
    answer_str = answer_str.strip()
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


def check_code_differ_by_just_empty_lines(code, prev_code):
    normalized_code1 = remove_empty_lines(code)
    normalized_code2 = remove_empty_lines(prev_code)
    return normalized_code1 == normalized_code2


class SweFixerVerifier(BaseVerifier):
    """
    Verifier for the SWE-Fixer dataset.
    https://github.com/InternLM/SWE-Fixer
    """


    def _patch_files_with_golden_patches(self, task_input):
        """
        Patch files with golden patches from the task input.
        This creates patched files using the ground truth patches for reference.
        
        Args:
            task_input: Dictionary containing task input data with modification instructions
            
        Returns:
            dict: Dictionary with file paths as keys and patched contents as values
        """
        patched_files = {}
        
        try:
            # Extract files to be modified from task input
            files_to_modify = task_input["metadata"]["input"]["files to be modified"]
            
            for file_info in files_to_modify:
                file_path = file_info["file"]
                file_content = remove_line_numbers(file_info["file content"])
                
                # Find the golden patch information from the task input
                golden_patches = task_input.get("verification_info", {}).get("golden_patches", [])
                
                for patch in golden_patches:
                    if patch["file"] == file_path:
                        code_snippet_to_be_modified = remove_line_numbers(
                            patch["code snippet to be modified"]
                        ).rstrip()
                        
                        correct_code_snippet = remove_line_numbers(
                            patch["correct code snippet"]
                        ).rstrip()
                        
                        # Apply the golden patch if the snippet is found in the file
                        if code_snippet_to_be_modified and code_snippet_to_be_modified in file_content:
                            new_content = file_content.replace(
                                code_snippet_to_be_modified, correct_code_snippet
                            )
                            patched_files[file_path] = new_content
                        elif file_content == "":  # Handle new file case
                            patched_files[file_path] = correct_code_snippet
            
            return patched_files
                
        except Exception as e:
            print(f"Error in patching files with golden patches: {e}")
            return {}

    def evaluate_task_code_editing(self, task_input, json_output):
        try:
            output = json.loads(json_output)
            files = output
        except Exception as e:
            # logger.error(f"Error in parsing json output for task code editing: {e}")
            # print(f"Error in parsing json output for task code editing: {e}")
            print(f"EXCEPTION: {e}")
            return "", ""
        try:
            git_diffs = ""
            raw_git_diffs = ""
            lint_success = False

            for file in files:
                # file_path = file["file path"]
                file_path = file["file"]
                code_snippet_to_be_modified = file["code snippet to be modified"]
                edited_code_snippet = file["edited code snippet"]

                code_snippet_to_be_modified = remove_line_numbers(
                    code_snippet_to_be_modified
                ).rstrip()

                file_content = ""
                for f in task_input["metadata"]["input"]["files to be modified"]:
                    if f["file"] == file_path:
                        file_content = remove_line_numbers(f["file content"])
                        break

                if (
                    code_snippet_to_be_modified
                    and code_snippet_to_be_modified in file_content
                ) or file_content == "":
                    if file_content:
                        new_content = file_content.replace(
                            code_snippet_to_be_modified, edited_code_snippet
                        )
                    else:  # new file
                        new_content = edited_code_snippet

                    syntax_success = check_syntax(new_content)

                    differ_by_empty_lines = check_code_differ_by_just_empty_lines(
                        new_content, file_content
                    )

                    if syntax_success and not differ_by_empty_lines:
                        return dict(score=1, verification_result_info={})
                    else:
                        return dict(score=0, verification_result_info={})
                else:
                    return dict(score=0, verification_result_info={})

        except Exception as e:
            breakpoint()
            return dict(score=0, verification_result_info={"failure_reason": "Error in evaluating task code editing for instance {instance_id}: {e}"})

    def verify(self, result: Response):
        """
        Evaluates the code patches by comparing the model's patches against golden patches.

        The score is either 0 or 1, representing whether the patches are correct.
        """

        verification_info = result["verification_info"]
        json_output = parse_json_codeblock_from_reasoning_model_output(result["llm_response"])

        return self.evaluate_task_code_editing(verification_info["input"], json_output)


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

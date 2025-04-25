### adapted from https://github.com/InternLM/SWE-Fixer/blob/main/evaluation/code_edit.py
import json
import os
import re
import ast
import argparse

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


def check_code_differ_by_just_empty_lines(code, prev_code):
    breakpoint()
    normalized_code1 = remove_empty_lines(code)
    normalized_code2 = remove_empty_lines(prev_code)
    return normalized_code1 == normalized_code2


class SweFixerVerifier(BaseVerifier):
    """
    Verifier for the SWE-Fixer dataset.
    https://github.com/InternLM/SWE-Fixer
    """


    def _patch_files_with_golden_patches(self, verification_info):
        """
        Create ground truth files by patching with golden patches from the original dataset's output.
        
        Args:
            verification_info: Dictionary containing verification info with modification instructions
            
        Returns:
            List of dictionaries with file paths and patched contents
        """
        patched_files = []
        
        try:
            # Get files to be modified from input
            files_to_modify = verification_info["input"]["files to be modified"]
            breakpoint()
            
            for file_info in files_to_modify:
                file_path = file_info["file"]
                file_content = remove_line_numbers(file_info["file content"])
                
                # Get golden patches from output
                golden_patches = verification_info["output"]["edited code"]
                
                for patch in golden_patches:
                    if patch["file"] == file_path:
                        code_snippet_to_be_modified = remove_line_numbers(
                            patch["code snippet to be modified"]
                        ).rstrip()
                        
                        edited_code_snippet = patch["edited code snippet"]
                        
                        # Apply the golden patch if the snippet is found in the file
                        if code_snippet_to_be_modified and code_snippet_to_be_modified in file_content:
                            new_content = file_content.replace(
                                code_snippet_to_be_modified, edited_code_snippet
                            )
                            patched_files.append({
                                "file": file_path,
                                "file content": new_content
                            })
                        elif file_content == "":  # Handle new file case
                            patched_files.append({
                                "file": file_path,
                                "file content": edited_code_snippet
                            })
            
            return patched_files
                
        except Exception as e:
            print(f"Error in patching files with golden patches: {e}")
            return []

    def evaluate_task_code_editing(self, verification_info, json_output):
        try:
            files = json.loads(json_output)
        except Exception as e:
            from pprint import pprint
            pprint("Verification info: ", verification_info)
            pprint("JSON output: ", json_output)
            raise e
            return "", ""
        try:
            for file in files:
                file_path = file["file"]
                code_snippet_to_be_modified = file["code snippet to be modified"]
                edited_code_snippet = file["edited code snippet"]

                code_snippet_to_be_modified = remove_line_numbers(
                    code_snippet_to_be_modified
                ).rstrip()

                file_content = ""
                patched_files = self._patch_files_with_golden_patches(verification_info)
                for patched_file in patched_files:
                    if patched_file["file"] == file_path:
                        file_content = patched_file["file content"]
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

                    differ_by_just_empty_lines = check_code_differ_by_just_empty_lines(
                        new_content, file_content
                    )

                    if syntax_success and differ_by_just_empty_lines:
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

### adapted from https://github.com/InternLM/SWE-Fixer/blob/main/evaluation/code_edit.py
import json
import os
import re
import ast

from genesys.schemas import Response
from genesys.verifiers.base_verifier import BaseVerifier


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


    @staticmethod
    def evaluate_task_code_editing(task_input, json_output, instance_id):
        try:
            output = json.loads(json_output)
            files = output
        except Exception as e:
            # logger.error(f"Error in parsing json output for task code editing: {e}")
            print(f"Error in parsing json output for task code editing: {e}")
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
            return dict(score=0, verification_result_info={"failure_reason": "Error in evaluating task code editing for instance {instance_id}: {e}"})

    def verify(self, result: Response):
        """
        Evaluates the code patches

        The score is a float between 0 and 1.
        """

        dataset_name = result["source"]
        entry = {"answer": result["verification_info"]["ground_truth"], "metadata": result["metadata"]}

        score = self.score_answer_fns[dataset_name](answer=result["llm_response"], entry=entry)
        return dict(score=score, verification_result_info={})

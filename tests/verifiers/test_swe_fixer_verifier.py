import json
from genesys.verifiers.registry import SweFixerVerifier


def test_swe_fixer_end_to_end_complex():
    """
    End-to-end check of SweFixerVerifier with two files and tricky indentation.
    The first patch fixes an indentation bug inside an `if`; the second renames
    a variable and tweaks the greeting text.
    """

    files_to_modify = [
        {
            "file": "utils/math_ops.py",
            "file content": (
                "1 def add(a, b):\n"
                "2     return a + b\n"
                "3 \n"
                "4 def divide(a, b):\n"
                "5     if b == 0:\n"
                "6     return None\n"            # bad – missing nested indent
                "7     return a / b\n"
            ),
        },
        {
            "file": "app/main.py",
            "file content": (
                "1 from utils.math_ops import add\n"
                "2 \n"
                "3 def greet(name):\n"
                "4     message = f\"Hello, {name}\"\n"
                "5     print(message)\n"
                "6 \n"
                "7 if __name__ == \"__main__\":\n"
                "8     print(add(2,3))\n"
            ),
        },
    ]

    correct_patches = [
        {
            "file": "utils/math_ops.py",
            "code snippet to be modified": (
                "4 def divide(a, b):\n"
                "5     if b == 0:\n"
                "6     return None\n"
                "7     return a / b"
            ),
            "edited code snippet": (
                "def divide(a, b):\n"
                "    if b == 0:\n"
                "        return None\n"
                "    return a / b"
            ),
        },
        {
            "file": "app/main.py",
            "code snippet to be modified": (
                "3 def greet(name):\n"
                "4     message = f\"Hello, {name}\"\n"
                "5     print(message)"
            ),
            "edited code snippet": (
                "def greet(name):\n"
                "    msg = f\"Hello, {name}!\"\n"
                "    print(msg)"
            ),
        },
    ]

    wrong_patches = [
        {
            "file": "utils/math_ops.py",
            "code snippet to be modified": (
                "4 def divide(a, b):\n"
                "5     if b == 0:\n"
                "6     return None\n"
                "7     return a / b"
            ),
            "edited code snippet": (
                "def divide(a, b):\n"
                "    if b == 0:\n"
                "    return None\n"      # missing indent will cause syntax error
                "    return a / b"
            ),
        }
    ]

    slightly_wrong_patches = [
        {
            "file": "utils/math_ops.py",
            "code snippet to be modified": (
                "4 def divide(a, b):\n"
                "5     if b == 0:\n"
                "6     return None\n"
                "7     return a / b"
            ),
            "edited code snippet": (
                "def divide_two_numbers(a, b):\n"
                "    if b == 0:\n"
                "        return 0\n"
                "    return a / b"
            ),
        },
        {
            "file": "app/main.py",
            "code snippet to be modified": (
                "3 def greet(name):\n"
                "4     message = f\"Hello, {name}\"\n"
                "5     print(message)"
            ),
            "edited code snippet": (
                "def greet_by_name(name):\n"
                "    message = f\"Hello, {name}!\"\n"
                "    print(message)"
            ),
        },
    ]


    verification_info = {
        "input":  {"files to be modified": files_to_modify},
        "output": {"edited code": correct_patches},
    }

    verifier = SweFixerVerifier()
    result_correct = {
        "problem_id": "test_swe_fixer_end_to_end_complex",
        "verification_info": verification_info,
        "llm_response": json.dumps(correct_patches),
    }
    result_wrong = {
        "problem_id": "test_swe_fixer_end_to_end_complex",
        "verification_info": verification_info,
        "llm_response": json.dumps(wrong_patches),
    }
    result_slightly_wrong = {
        "problem_id": "test_swe_fixer_end_to_end_complex",
        "verification_info": verification_info,
        "llm_response": json.dumps(slightly_wrong_patches),
    }
    score_dict_correct = verifier.verify(result_correct)
    score_dict_wrong = verifier.verify(result_wrong)
    score_dict_slightly_wrong = verifier.verify(result_slightly_wrong)

    assert score_dict_correct["score"] == 1.0, f"unexpected verifier score: {score_dict_correct}"
    assert score_dict_wrong["score"] == 0.0, f"unexpected verifier score: {score_dict_wrong}"
    assert 0 < score_dict_slightly_wrong["score"] < 1.0, f"unexpected verifier score: {score_dict_slightly_wrong}"
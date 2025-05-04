# tests/test_swe_fixer_end_to_end.py
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

    golden_patches = [
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

    verification_info = {
        "input":  {"files to be modified": files_to_modify},
        "output": {"edited code": golden_patches},
    }

    verifier = SweFixerVerifier()
    result = {
        "problem_id": "test_swe_fixer_end_to_end_complex",
        "verification_info": verification_info,
        "llm_response": json.dumps(golden_patches),
    }
    score_dict = verifier.verify(result)

    assert score_dict["score"] == 1.0, f"unexpected verifier score: {score_dict}"

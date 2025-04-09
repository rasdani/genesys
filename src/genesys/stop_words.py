import sglang as sgl
from transformers import AutoTokenizer
import re


def parse_tool_call(text):
    # Get the everthing after the last </search> tag
    search_match = re.search(r"</search>(.*)", text)
    if search_match:
        return search_match.group(1).strip()
    else:
        return ""

def get_tool_response(query):

    tool_responses = {
        "show": "<result>Mr. Robot</result>",
        "sister": "<result>Darlene</result>",
        "main character": "<result>Elliot</result>"
    }
    if "show" in query:
        return tool_responses["show"]
    elif "sister" in query:
        return tool_responses["sister"]
    elif "main character" in query:
        return tool_responses["main character"]
    else:
        return "<result>SEARCH FAILED, REPHRASE YOUR QUERY</result>"

def test_stop_words():
    # Initialize the model
    model_path = "Qwen/Qwen2.5-7B-Instruct"  # Using the same model as your main script
    llm = sgl.Engine(
        model_path=model_path,
        tp_size=1,  # Using just 1 GPU for testing
    )
    
    # Test prompt
    prompt = "For the following question, you MUST AT ALL COSTS call a search tool inside <search>...</search> tags. Question: Who is sister of the main character in Sam Esmail's most successful show?"

    
    # Basic stop on EOS and double newline
    stop = ["</search>"]

    # Prepare sampling parameters
    sampling_params = {
        "temperature": 0.7,
        "top_p": 0.95,
        "max_new_tokens": 1000,
        "stop": stop
    }
    
    text = ""
    while True:
        input = text if text else prompt
        response = llm.generate(
            input,
            sampling_params=sampling_params
        )
        finish_reason = response["meta_info"]["finish_reason"]
        text = response["text"]
        if finish_reason == "stop":
            tool_call = parse_tool_call(text)
            tool_response = get_tool_response(tool_call)
            text += "</search>" + tool_response
            print(f"FINISH REASON: {finish_reason}")
            print(f"RESPONSE: {response}")
            print(f"TEXT: {text}")
        else:
            print(f"FINISH REASON: {finish_reason}")
            print(f"RESPONSE: {response}")
            print(f"TEXT: {text}")
            break
        
        # Decode and print the response
        print("-" * 50)
        print(f"Response: {text}")


if __name__ == "__main__":
    test_stop_words()

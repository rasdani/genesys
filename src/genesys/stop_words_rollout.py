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

@sgl.function
def generate_with_search(s, prompt, max_tokens=1000, temperature=0.7, top_p=0.95):
    # Initialize the generation
    s += prompt
    
    # Generate until we get a search tag or finish
    while True:
        # Generate with stop on search tag
        s += sgl.gen(
            "text",
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=["</search>", "\n\n"]
        )
        
        # Check if we got a search tag
        if "</search>" in s["text"]:
            # Extract the search query
            search_query = parse_tool_call(s["text"])
            
            # Get the tool response
            tool_response = get_tool_response(search_query)
            
            # Add the tool response and continue generation
            s += tool_response
        else:
            # No search tag found, we're done
            break
    
    return s["text"]

def test_stop_words():
    # Initialize the model
    model_path = "Qwen/Qwen2.5-7B-Instruct"
    llm = sgl.Engine(
        model_path=model_path,
        tp_size=1,
    )
    
    # Test prompt
    prompt = "For the following question, you MUST AT ALL COSTS call a search tool inside <search>...</search> tags. Question: Who is sister of the main character in Sam Esmail's most successful show?"
    
    # Run the generation
    result = generate_with_search(llm, prompt)
    
    # Print the result
    print("-" * 50)
    print(f"Final Response: {result}")

if __name__ == "__main__":
    test_stop_words()

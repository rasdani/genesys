import sglang as sgl
from sglang import set_default_backend

def minimal_test():
    # Set the backend
    set_default_backend(sgl.RuntimeEndpoint("http://localhost:30000"))
    
    # Initialize the model
    model_path = "Qwen/Qwen2.5-1.5B-Instruct"
    llm = sgl.Engine(
        model_path=model_path,
        tp_size=1
    )
    
    # Simple prompt
    prompt = "What is the capital of France?"
    
    # Approach 1: Using llm.generate (stateless)
    # sampling_params = {
    #     "temperature": 0.7,
    #     "max_new_tokens": 50
    # }
    # response = llm.generate(
    #     prompt,
    #     sampling_params=sampling_params
    # )
    # print("=== Using llm.generate ===")
    # print(f"Prompt: {prompt}")
    # print(f"Response: {response['text']}")
    # print("-" * 50)
    
    # Approach 2: Using sgl.gen (stateful)
    @sgl.function
    def generate_with_state(s, prompt):
        s += prompt
        s += sgl.gen("answer", max_tokens=50, temperature=0.7)
        return s["answer"]
    
    result = generate_with_state(llm, prompt)
    print("=== Using sgl.gen ===")
    print(f"Prompt: {prompt}")
    print(f"Response: {result}")
    print("-" * 50)

if __name__ == "__main__":
    minimal_test() 
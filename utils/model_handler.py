import os
import requests
from dotenv import load_dotenv

# Explicitly load .env file
load_dotenv(dotenv_path="cred.env")

def get_model_config(model):
    """
    Returns the URL and headers for the given model by reading from environment variables.
    """
    if model == "GPT-4o_finetuned":
        url = os.getenv("GPT4O_FINETUNED_URL")
        headers = {
            "Content-Type": "application/json",
            "api-key": os.getenv("GPT4O_FINETUNED_API_KEY")
        }
    elif model == "GPT-4_notfinetuned":
        url = os.getenv("GPT4_NOT_FINETUNED_URL")
        headers = {
            "Content-Type": "application/json",
            "api-key": os.getenv("GPT4_NOT_FINETUNED_API_KEY")
        }
    elif model == "LLaMA_finetuned":
        url = os.getenv("LLAMA_FINETUNED_URL")
        headers = {
            "Authorization": f"Bearer {os.getenv('LLAMA_FINETUNED_BEARER')}",
            "Content-Type": "application/json"
        }
    elif model == "LLaMA_notfinetuned":
        url = os.getenv("LLAMA_NOT_FINETUNED_URL")
        headers = {
            "Authorization": f"Bearer {os.getenv('LLAMA_NOT_FINETUNED_BEARER')}",
            "Content-Type": "application/json"
        }
    else:
        raise ValueError(f"⚠️ Unknown model selected: {model}")

    print(f"Using url: {url} and headers: {headers}")
    if not url or not headers:
        raise EnvironmentError(f"⚠️ Missing environment variables for model: {model}")

    return url, headers

def get_response(model, context, history, prompt):
    """
    Prepares payload, sends request to model endpoint, and returns the model response.
    """
    try:
        # # 🚀 Merge context and prompt manually
        # combined_prompt = (context + "\n\n" + prompt) if context else prompt

        # # Only 'user' role everywhere
        # messages = [{"role": "user", "content": combined_prompt}]



        messages = []
        # Add system prompt if context is provided
        if context:
            messages.append({"role": "system", "content": context})

        # Add chat history
        for entry in history:
            messages.append({"role": "user", "content": entry["user"]})
            messages.append({"role": "assistant", "content": entry["response"]})
            
        # Add the new user prompt
        messages.append({"role": "user", "content": prompt})

        # Prepare payload based on model type
        if model in ["GPT-4_notfinetuned", "GPT-4o_finetuned"]:
            payload = {
                "messages": messages,
                "temperature": 1
            }
        else:  # For LLaMA models (Databricks)
            payload = {
                "messages": messages
                # 🚨 No temperature key for Databricks models
            }

        # Get URL and Headers securely
        url, headers = get_model_config(model)

        # Make POST request
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            return f"⚠️ Error: {response.status_code}, Details: {response.text}"

        result = response.json()

        if "choices" in result:  # OpenAI format
            return result["choices"][0]["message"]["content"]
        elif "predictions" in result:  # Databricks format (optional if needed)
            return result["predictions"][0]
        else:
            return f"⚠️ Unexpected response format: {result}"

    except Exception as e:
        return f"⚠️ Error communicating with model: {str(e)}"

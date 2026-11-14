import openai
from openai import OpenAI
import os
import numpy as np
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

class LLM:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAPI_KEY"))

    def get_completion(self, prompt, model='gpt-4o-mini'):
        message = {'role': 'user', 'content': prompt}
        response = self.client.chat.completions.create(
            model=model,
            messages=[message]
        )
        return response.choices[0].message.content



if __name__ == "__main__":
    llm_client = LLM()
    model = 'gpt-4o-mini'
    prompt = "What is baseball?"
    print(llm_client.get_completion(prompt, model))
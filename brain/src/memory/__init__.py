from dotenv import load_dotenv
import os
from groq import Groq

load_dotenv()

GROQ_API = os.getenv("GROQ_API")

client = Groq(
    api_key=GROQ_API,
)
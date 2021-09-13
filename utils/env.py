from pathlib import Path
import os
from dotenv import load_dotenv


def comma_check(param):
    if "," in param:
        return param.split(",")
    return param


def load_params(required_params):
    env_path = Path(".") / ".env"
    load_dotenv(dotenv_path=env_path)
    return {param.lower(): comma_check(os.getenv(param)) for param in required_params}

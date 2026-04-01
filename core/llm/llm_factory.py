import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from core.logging import get_logger

logger = get_logger("CORE")
load_dotenv()


def get_llm():
    model_name = os.getenv("EDUCLAW_MODEL_NAME")
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL")

    if not model_name:
        logger.critical("Missing EDUCLAW_MODEL_NAME in .env")
        raise ValueError("未找到模型配置")

    logger.info(f"LLM Factory: Initializing [bold white]{model_name}[/bold white]", extra={"markup": True})

    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base=base_url,
        # temperature=0.7
    )
"""
初始化大模型

Author: Gongmin Wei
Date: 2026-04-01
"""
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from core.logging import get_logger

logger = get_logger("CLIENT")
load_dotenv()


def get_llm(test_connection_test: bool = True) -> ChatOpenAI:
    """初始化LLM。"""
    model_name = os.getenv("EDUCLAW_MODEL_NAME")
    api_key = os.getenv("EDUCLAW_MODEL_API_KEY")
    base_url = os.getenv("EDUCLAW_MODEL_API_URL")

    if not model_name:
        logger.critical("LLM Factory: LLM初始化失败--环境变量 EDUCLAW_MODEL_NAME 未配置")
        raise ValueError("EDUCLAW_MODEL_NAME cannot be empty")

    if not api_key:
        logger.critical("LLM Factory: LLM初始化失败--环境变量 EDUCLAW_MODEL_API_KEY 未配置")
        raise ValueError("EDUCLAW_MODEL_API_KEY cannot be empty")

    if not base_url:
        logger.critical("LLM Factory: LLM初始化失败--环境变量 EDUCLAW_MODEL_API_URL 未配置")
        raise ValueError("EDUCLAW_MODEL_API_URL cannot be empty")

    logger.info(f"LLM Factory: 正在初始化模型--[bold white]{model_name}[/bold white] ...", extra={"markup": True})

    llm = ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base=base_url,
        # temperature=0.7
    )

    if test_connection_test:
        logger.info("LLM Factory: 正在测试模型是否可用 ...")

        try:
            llm.invoke({
                "messages": [
                    ("human", "模型连接测试")
                ]
            })
            logger.info(f"LLM Factory: [bold green]模型 {model_name} 可用[/bold green]")
        except Exception as e:
            logger.error(f"LLM Factory: 模型 [bold orange1]{model_name}[/bold orange1] 连接测试失败： {str(e)}")
            raise ConnectionError(f"Failed to connect to LLM model.Please check your API_KEY, BASE_URL, or network connection: {str(e)}")

    return llm


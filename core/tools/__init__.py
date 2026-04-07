from .document_pro import extract_pdf
from .document_pro import extract_word
from .document_pro import extract_pptx
from .sandbox import run_python_code, run_python_file
from .weather_tool import get_weather

all_tools = [
    extract_pdf, extract_word, extract_pptx,
    run_python_code, run_python_file, get_weather
]
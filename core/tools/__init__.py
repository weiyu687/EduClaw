from .document_pro import extract_pdf, extract_word, extract_pptx, extract_xlsx
from .sandbox import run_python_code, run_python_file, extract_py
from .get_all_files import get_all_files
from .doc_retrieve import process_doc
from .weather_tool import get_weather

all_tools = [
    extract_pdf, extract_word, extract_pptx, extract_xlsx,
    run_python_code, run_python_file, extract_py, get_all_files,
    process_doc, get_weather
]
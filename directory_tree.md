# Project Directory Tree
```
├── apps
│   └── ubuntu
├── assets
│   ├── bluelobster.png
│   ├── bluelobster_px.png
│   └── logo.png
├── core
│   ├── agent
│   │   ├── adaptor.py
│   │   ├── agent_factory.py
│   │   ├── memory_agent.py
│   │   └── __init__.py
│   ├── error_handling
│   │   ├── adaptor_integration.py
│   │   ├── error_handler.py
│   │   ├── exceptions.py
│   │   ├── recovery.py
│   │   ├── validator.py
│   │   └── __init__.py
│   ├── llm
│   │   ├── llm_factory.py
│   │   └── __init__.py
│   ├── logging
│   │   ├── logger.py
│   │   └── __init__.py
│   ├── mcp
│   │   ├── client.py
│   │   ├── server.py
│   │   ├── startup_server.py
│   │   └── __init__.py
│   ├── memory
│   │   ├── base.py
│   │   ├── chroma_storage.py
│   │   ├── memory_manager.py
│   │   ├── utils.py
│   │   └── __init__.py
│   ├── scripts
│   ├── tools
│   │   ├── document_pro
│   │   │   ├── extract_pdf.py
│   │   │   ├── extract_pptx.py
│   │   │   ├── extract_word.py
│   │   │   ├── extract_xlsx.py
│   │   │   └── __init__.py
│   │   ├── doc_retrieve
│   │   │   ├── manage_vectordb.py
│   │   │   ├── process_doc.py
│   │   │   ├── retrieve_knowledge.py
│   │   │   └── __init__.py
│   │   ├── memory
│   │   ├── sandbox
│   │   │   ├── docker_executor.py
│   │   │   ├── extract_py.py
│   │   │   ├── run_python_code.py
│   │   │   ├── run_python_file.py
│   │   │   └── __init__.py
│   │   ├── get_all_files.py
│   │   ├── weather_tool.py
│   │   └── __init__.py
│   ├── usr
│   │   ├── main.py
│   │   └── startup_info.py
│   ├── utils
│   │   └── __init__.py
│   └── __init__.py
├── docs
│   └── skills
│       └── document-pro
│           └── SKILL.md
├── logs
│   └── educlaw.log
├── models
│   └── all-MiniLM-L6-v2
│       ├── config.json
│       ├── pytorch_model.bin
│       ├── special_tokens_map.json
│       ├── tokenizer.json
│       ├── tokenizer_config.json
│       └── vocab.txt
├── playground
│   └── llm_factory.py
├── prompts
│   └── agent.prompt
├── skills
│   ├── document-pro
│   │   └── SKILL.md
│   ├── doc_retrieve
│   │   └── SKILL.md
│   ├── homework-grader
│   │   └── SKILL.md
│   └── sandbox
│       └── SKILL.md
├── test
│   ├── batch_run_code
│   │   ├── 2026001.py
│   │   ├── 2026002.py
│   │   ├── 2026003.py
│   │   ├── 2026004.py
│   │   └── 2026005.py
│   ├── tools
│   │   ├── document_pro
│   │   │   ├── test_data
│   │   │   │   ├── dual_page_with_tables.doc
│   │   │   │   ├── dual_page_with_tables.docx
│   │   │   │   ├── dual_page_with_tables.pdf
│   │   │   │   ├── test.pptx
│   │   │   │   └── test.xlsx
│   │   │   ├── extract_md.py
│   │   │   ├── extract_pdf.test.py
│   │   │   ├── extract_pptx.test.py
│   │   │   ├── extract_txt.test.py
│   │   │   ├── extract_word.test.py
│   │   │   └── extract_xlsx.test.py
│   │   ├── doc_retrieve
│   │   │   ├── test_data
│   │   │   │   └── A_Byte_of_Python.pdf
│   │   │   ├── process_doc.test.py
│   │   │   └── retrieve_knowledge.test.py
│   │   ├── sandbox
│   │   │   ├── test_data
│   │   │   │   ├── codeerr.py
│   │   │   │   ├── normal.py
│   │   │   │   └── timeout.py
│   │   │   ├── docker_executor.py
│   │   │   ├── extract_py.test.py
│   │   │   ├── run_python_code.test.py
│   │   │   └── run_python_file.test.py
│   │   └── get_all_files.py
│   ├── README.md
│   ├── test_agent_memory_e2e.py
│   └── test_memory_system.py
├── ui
├── .env
├── .gitignore
├── README.md
└── script.py
```
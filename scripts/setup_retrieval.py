"""Explicit one-time download. Chat/query code never downloads model weights."""
import os
from pathlib import Path
import sys
os.environ.setdefault('HF_HUB_DISABLE_XET','1')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    from huggingface_hub import snapshot_download
    from core.state.semantic import MODEL_ID,REVISION,DEFAULT_MODEL
    snapshot_download(MODEL_ID,revision=REVISION,local_dir=str(DEFAULT_MODEL),
                      allow_patterns=['config.json','tokenizer.json','model.safetensors','README.md'])
    from model2vec import StaticModel
    model=StaticModel.from_pretrained(str(DEFAULT_MODEL))
    assert model.encode(['初始化检索']).shape[1]==256
    print('Local multilingual retrieval model installed and verified.')

if __name__=='__main__':main()

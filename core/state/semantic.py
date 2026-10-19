"""Local static embeddings. No remote code, GPU, or request-time downloads."""
from collections import OrderedDict
import hashlib
import os
from pathlib import Path
import threading

MODEL_ID='minishlab/potion-multilingual-128M'
REVISION='73908c3438cf03b6a01bcb9611d62b23d0726f08'
DEFAULT_MODEL=Path(__file__).resolve().parents[2]/'models'/'potion-multilingual-128M'
_lock=threading.RLock()
_model=None
_key=None
_vectors=OrderedDict()
_error=''

def model_path():return Path(os.environ.get('EDUCLAW_RETRIEVAL_MODEL',str(DEFAULT_MODEL)))

def status():
    path=model_path()
    ready=all((path/f).is_file() for f in ('config.json','tokenizer.json','model.safetensors'))
    disabled=os.environ.get('EDUCLAW_RETRIEVAL_MODE')=='lexical'
    return {'engine':'hybrid-static-rrf' if ready and not disabled and not _error else 'bm25-fallback',
            'model':MODEL_ID,'revision':REVISION,'local_only':True,'ready':ready and not disabled and not _error,
            'notice':_error or ('已选择关键词模式。' if disabled else '' if ready else '语义模型未安装，当前使用关键词回退；运行 python scripts/setup_retrieval.py。')}

def similarities(query,rows):
    global _model,_key,_error
    if os.environ.get('EDUCLAW_RETRIEVAL_MODE')=='lexical':return None
    path=model_path()
    if not all((path/f).is_file() for f in ('config.json','tokenizer.json','model.safetensors')):return None
    with _lock:
        try:
            import numpy as np
            key=str(path.resolve())
            if _model is None or key!=_key:
                from model2vec import StaticModel
                _model=StaticModel.from_pretrained(key);_key=key;_vectors.clear()
            texts=[query]+[row['text'] for row in rows]
            keys=[hashlib.sha256(text.encode()).hexdigest() for text in texts]
            missing={k:text for k,text in zip(keys,texts) if k not in _vectors}
            if missing:
                encoded=_model.encode(list(missing.values()))
                encoded=encoded/np.maximum(np.linalg.norm(encoded,axis=1,keepdims=True),1e-9)
                for k,v in zip(missing,encoded):_vectors[k]=v
            matrix=np.asarray([_vectors[k] for k in keys])
            for k in keys:_vectors.move_to_end(k)
            while len(_vectors)>8192:_vectors.popitem(last=False)
            _error=''
            return (matrix[1:]@matrix[0]).tolist()
        except Exception:
            # Don't expose provider paths or credentials; failure remains visible.
            _error='本地语义检索不可用，已回退关键词检索；请检查检索依赖和模型文件。'
            return None

import contextvars
from contextlib import contextmanager
from core.security.code_approval import fingerprint
_review=contextvars.ContextVar('reviewed_write',default=None)

@contextmanager
def reviewed_write(arguments, tool='write_text_file'):
    token=_review.set([fingerprint(tool,arguments),False])
    try:yield
    finally:_review.reset(token)

def consume(arguments, tool='write_text_file'):
    item=_review.get()
    if item and not item[1] and item[0]==fingerprint(tool,arguments):
        item[1]=True
        return True
    return False

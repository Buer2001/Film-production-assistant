def normalize_text(content):
    """统一换行后保存；证据位置始终对应这份保存的文本。"""
    return content.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')

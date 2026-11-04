# 文件职责：规范剧本文本换行，后续证据偏移始终对应保存后的原文。
# 用途：移除开头 BOM 并统一换行。
# 参数：content 为剧本文本字符串。
# 返回及副作用：返回以 LF 为换行的字符串，不修改其他原文内容。
def normalize_text(content):
    """统一换行后保存；证据位置始终对应这份保存的文本。"""
    return content.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')

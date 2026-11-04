# 文件职责：统一文本兼容字符及首尾空白，提供保序去重能力。
import unicodedata


# 用途：规范一段用于匹配的文本。
# 参数：value 为字符串。
# 返回及副作用：返回 NFKC 规范化后去掉首尾空白的字符串，不修改输入。
def normalized(value):
    return unicodedata.normalize('NFKC', value).strip()


# 用途：对文本列表规范化、过滤空值并保序去重。
# 参数：values 为字符串可迭代对象。
# 返回及副作用：返回规范化后的唯一字符串列表，不修改输入。
def unique(values):
    return list(dict.fromkeys(normalized(v) for v in values if normalized(v)))


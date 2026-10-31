import unicodedata


def normalized(value):
    return unicodedata.normalize('NFKC', value).strip()


def unique(values):
    return list(dict.fromkeys(normalized(v) for v in values if normalized(v)))


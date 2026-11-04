# 文件职责：使用标准库生成拆解及变更说明两张工作表的 XLSX 字节内容。
from io import BytesIO
import json
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape

COLUMNS = [('scene_number', '场号'), ('interior_exterior', '内外'), ('atmosphere', '气氛'),
           ('word_count', '字数'), ('location', '场景'), ('summary', '内容'),
           ('cast', '角色'), ('makeup_costume', '妆造'), ('action_props', '戏用道具'),
           ('other_props', '其他道具'), ('notes', '备注')]


# 用途：将单元格值转换为展示文本。
# 参数：value 可为空、列表或其他值。
# 返回及副作用：返回字符串；列表中的字典拼接非空值，None 转为空文本。
def display(value):
    if value is None:
        return ''
    if isinstance(value, list):
        return '；'.join(' / '.join(str(v) for v in item.values() if v) if isinstance(item, dict) else str(item) for item in value)
    return str(value)


# 用途：构建一张工作表的 OOXML。
# 参数：rows 为按行组织的单元格值列表。
# 返回及副作用：返回工作表 XML 字符串；计算 Excel 列号、过滤非法控制字符并转义，所有值用 inlineStr 防止公式执行。
def sheet(rows):
    lines = []
    for n, values in enumerate(rows, 1):
        cells = []
        for i, value in enumerate(values):
            number, column = i + 1, ''
            while number:
                number, rem = divmod(number - 1, 26)
                column = chr(65 + rem) + column
            # inlineStr 强制按文本输出，避免道具名等内容被 Excel 当作公式执行。
            safe = ''.join(c for c in display(value) if ord(c) >= 32 or c in '\t\n\r')
            cells.append(f'<c r="{column}{n}" t="inlineStr"><is><t xml:space="preserve">{escape(safe)}</t></is></c>')
        lines.append(f'<row r="{n}">{"".join(cells)}</row>')
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(lines) + '</sheetData></worksheet>'


# 用途：将工作台文档打包为 XLSX。
# 参数：doc 含剧本元数据、场次、差异及可选自定义字段。
# 返回及副作用：返回 ZIP 格式的工作簿字节；包含启用自定义列、原文及顺序差异，不写磁盘。
def export_workbook(doc):
    """只导出传入快照；用标准库生成基础 XLSX，不引入文件处理依赖。"""
    metadata = [doc['title'], f"剧本 V{doc['version_number']} {doc['version_label']}",
                f"编辑版本 {doc['revision']}", '已确认' if doc['status'] == 'confirmed' else '未确认',
                doc['confirmed_at'] or '']
    fields = [field for field in doc.get('custom_fields', []) if field.get('active', True)]
    rows = [metadata, [label for _, label in COLUMNS] + [field['name'] for field in fields]]
    for row in doc['scenes']:
        values = []
        for key, _ in COLUMNS:
            value = row.get(key)
            if key in ('action_props', 'other_props'):
                value = '、'.join(item['name'] for item in (value or []))
            values.append(value)
        values.extend(row.get('custom_values', {}).get(field['id'], '') for field in fields)
        rows.append(values)
    changes = [['类型', '场号', '变化字段', '上一版', '本版']]
    for row in doc['comparison']['changed']:
        # 用途：序列化某一侧实际变更字段。
        # 参数：side 为 before 或 after，闭包 row 为差异项，fields 为启用自定义字段。
        # 返回及副作用：返回 JSON 字符串；分别处理原文、顺序、道具名及自定义列展示名，不修改差异项。
        def changed_values(side):
            values = {}
            for key in row['fields']:
                if key == '原文':
                    values[key] = row[side]['evidence'].get('text', '')
                elif key == '顺序':
                    values[key] = row[side + '_order']
                elif key in ('action_props', 'other_props'):
                    values[key] = [item['name'] for item in (row[side].get(key) or [])]
                elif key == 'custom_values':
                    values[key] = {field['name']: row[side].get(key, {}).get(field['id'], '') for field in fields}
                else:
                    values[key] = row[side].get(key)
            return json.dumps(values, ensure_ascii=False)
        changes.append(['修改', row['scene_number'], '、'.join(row['fields']),
                        changed_values('before'), changed_values('after')])
    for kind, label in [('added', '新增'), ('deleted', '删除')]:
        for row in doc['comparison'][kind]:
            changes.append([label, row['scene_number'], '', row['summary'] if kind == 'deleted' else '',
                            row['summary'] if kind == 'added' else ''])
    # 未关联旧场次和待匹配新场次单独标识，不把尚未确认的对应关系直接导出为删除或新增。
    for row in doc['comparison'].get('unlinked', []):
        changes.append(['未关联旧场次（未确认删除）', row['scene_number'], '', row.get('summary', ''), ''])
    by_id = {row['id']: row for row in doc['scenes']}
    for item in doc['comparison'].get('pending', []):
        row = by_id.get(item['id'], {})
        changes.append(['待匹配（未确认新增）', row.get('scene_number', ''), '', '', row.get('summary', '')])
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="剧本拆解" sheetId="1" r:id="rId1"/><sheet name="变更说明" sheetId="2" r:id="rId2"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', sheet(rows))
        z.writestr('xl/worksheets/sheet2.xml', sheet(changes))
    return output.getvalue()

"""Run offline contract evaluations: python -m evaluations.run [--output PATH]."""
import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


# 用途：运行选定的离线业务契约测试，读取 JUnit 结果并生成 JSON 评估报告。
# 参数：通过命令行 --output 指定报告路径，默认 docs/evaluation-report.json。
# 返回：退出码整数；优先沿用测试进程的非零退出码，进程成功且有报告用例时为 0，否则为 1。
# 限制：使用模拟模型和测试数据库，报告不能证明真实模型准确率或线上可用性。
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='docs/evaluation-report.json')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temp:
        report = Path(temp) / 'results.xml'
        process = subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_analysis.py',
            'tests/test_workflow.py', 'tests/test_scripts_v1.py', 'tests/test_streaming.py',
            'tests/test_draft_tools.py', 'tests/test_empty_placeholder.py', '-q', f'--junitxml={report}'], cwd=root)
        # 从每个用例提取状态和耗时；同时保留失败摘要，便于报告定位回归。
        cases = []
        if report.exists():
            for case in ElementTree.parse(report).iter('testcase'):
                failure = case.find('failure')
                error = case.find('error')
                failed = failure if failure is not None else error
                cases.append({'scenario': case.attrib['name'],
                    'status': 'failed' if failed is not None else 'skipped' if case.find('skipped') is not None else 'passed',
                    'seconds': float(case.attrib.get('time', 0)),
                    **({'detail': failed.attrib.get('message', '')} if failed is not None else {})})
    passed = sum(c['status'] == 'passed' for c in cases)
    data = {'generated_at': datetime.now(timezone.utc).isoformat(),
        'mode': 'offline_mock_model', 'total': len(cases), 'passed': passed,
        'contract_pass_rate': passed / len(cases) if cases else 0,
        'limitations': '模拟模型和SQLite业务契约回归；不代表真实模型提取准确率、抗提示注入效果或PostgreSQL验证。',
        'scenarios': cases}
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Evaluation: {passed}/{len(cases)} passed; report: {output}')
    return process.returncode or (0 if cases else 1)


if __name__ == '__main__':
    raise SystemExit(main())

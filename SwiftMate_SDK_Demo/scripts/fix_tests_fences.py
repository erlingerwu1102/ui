import pathlib

TEST_DIR = pathlib.Path(__file__).resolve().parent.parent / 'tests'
print('Scanning', TEST_DIR)
for p in TEST_DIR.glob('test_*.py'):
    text = p.read_text(encoding='utf-8')
    new_lines = []
    changed = False
    for line in text.splitlines():
        if line.strip() == '```' or line.strip() == '```python':
            changed = True
            continue
        new_lines.append(line)
    if changed:
        p.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')
        print('Fixed', p)
    else:
        print('No change', p)
print('Done')

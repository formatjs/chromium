"""Compare capture modes against the exact failed cold artifact."""
import collections
import json
import os
from pathlib import Path
import shutil

from tools.ci import check_rendering
from tools.ci.chromium import PLATFORMS, unpack

temporary = Path(os.environ['RUNNER_TEMP'])
output = temporary / 'capture-probe'
output.mkdir()
revision = '85f68a703a15439fd9aca037b431aa0f1416c053'
bundle = unpack(temporary / 'artifact/chromium-linux-arm64.tar.gz',
                temporary / 'unpacked-probe', PLATFORMS['linux-arm64'], revision)
original = check_rendering.DevTools.command
mode = 'original'


def command(self, method, params=None):
    if method == 'Page.captureScreenshot' and mode == 'viewport':
        params = {**params, 'captureBeyondViewport': True,
                  'clip': {'x': 0, 'y': 0, 'width': 800, 'height': 600, 'scale': 1}}
    return original(self, method, params)


check_rendering.DevTools.command = command
results = []
for index in range(60):
    for mode in (('original', 'viewport') if index % 2 == 0 else ('viewport', 'original')):
        directory = output / (mode + '-' + str(index))
        error = None
        try:
            report = check_rendering.check(bundle / 'chrome', directory)
        except Exception as caught:
            error = str(caught)
            report = json.loads((directory / 'report.json').read_text()) if (directory / 'report.json').exists() else {}
        row = {'mode': mode, 'iteration': index, 'passed': report.get('passed', False),
               'cases': report.get('cases'), 'error': error}
        results.append(row)
        (output / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps({'mode': mode, 'iteration': index, 'passed': row['passed'],
                          'changed': {k: v.get('changed_pixels') for k, v in (row['cases'] or {}).items()}}), flush=True)
        if row['passed']:
            shutil.rmtree(directory)
print(json.dumps({mode: dict(collections.Counter(row['passed'] for row in results if row['mode'] == mode))
                  for mode in ['original', 'viewport']}), flush=True)

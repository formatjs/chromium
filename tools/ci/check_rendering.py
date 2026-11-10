"""Render local fixtures and compare font-independent scenes with reviewed PNGs."""

import argparse
import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

from PIL import Image, ImageChops, ImageStat
import websocket

from overlays.chromium.tools.check_browser import browser_version, run, serve_page
from tools.ci.chromium import CONFIGURATION


FIXTURES = Path(__file__).with_name('rendering')
VIEWPORT = (800, 600)
SCENE = (40, 150, 760, 510)
CASES = {
    'layout': {'scene': [40, 150, 720, 360], 'a': [62, 172, 161, 120],
               'b': [239, 172, 322, 120], 'e': [239, 308, 322, 180]},
    'graphics': {'scene': [40, 150, 720, 360]},
}


class DevTools:
    def __init__(self, connection):
        self.connection = connection
        self.identifier = 0

    def command(self, method, params=None):
        self.identifier += 1
        self.connection.send(json.dumps({'id': self.identifier, 'method': method,
                                         'params': params or {}}))
        while True:
            message = self.connection.recv()
            if not message:
                raise RuntimeError('DevTools disconnected')
            response = json.loads(message)
            if response.get('id') != self.identifier:
                continue
            if 'error' in response:
                raise RuntimeError('DevTools error: ' + str(response['error']))
            return response.get('result', {})

    def navigate(self, url, timeout):
        navigation = self.command('Page.navigate', {'url': url})
        if navigation.get('errorText'):
            raise RuntimeError(navigation['errorText'])
        deadline = time.monotonic() + timeout
        expression = ('location.href === ' + json.dumps(url)
                      + " && document.readyState === 'complete'"
                      + " && document.getElementById('result')?.textContent")
        while time.monotonic() < deadline:
            response = self.command('Runtime.evaluate', {
                'expression': expression, 'returnByValue': True,
            })
            value = response.get('result', {}).get('value')
            if value and value != 'pending':
                self.command('Runtime.evaluate', {
                    'expression': 'new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))',
                    'awaitPromise': True,
                })
                return json.loads(value)
            time.sleep(0.05)
        raise TimeoutError('Rendering fixture did not become ready: ' + url)


@contextmanager
def browser_session(browser, flags, environment, directory, output, timeout):
    profile = directory / 'profile'
    connection = None
    with (output / 'browser.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([
            str(browser), *flags, '--remote-debugging-port=0',
            '--user-data-dir=' + str(profile), 'about:blank',
        ], cwd=directory, env=environment, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + timeout
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Browser exited before DevTools startup; inspect browser.log')
                try:
                    port = int((profile / 'DevToolsActivePort').read_text().splitlines()[0])
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=1) as response:
                        targets = json.load(response)
                    target = next(item for item in targets if item.get('type') == 'page')
                    break
                except (OSError, StopIteration, ValueError):
                    if time.monotonic() >= deadline:
                        raise TimeoutError('DevTools startup timed out; inspect browser.log')
                    time.sleep(0.05)
            connection = websocket.create_connection(target['webSocketDebuggerUrl'],
                                                     timeout=timeout, suppress_origin=True)
            session = DevTools(connection)
            session.command('Page.enable')
            window = session.command('Browser.getWindowForTarget')
            viewport = session.command('Runtime.evaluate', {
                'expression': '({width: innerWidth, height: innerHeight})',
                'returnByValue': True,
            })['result']['value']
            # Size native surface before overriding renderer viewport.
            session.command('Browser.setWindowBounds', {
                'windowId': window['windowId'],
                'bounds': {
                    'width': window['bounds']['width'] + VIEWPORT[0] - viewport['width'],
                    'height': window['bounds']['height'] + VIEWPORT[1] - viewport['height'],
                },
            })
            session.command('Emulation.setDeviceMetricsOverride', {
                'width': VIEWPORT[0], 'height': VIEWPORT[1],
                'deviceScaleFactor': 1, 'mobile': False,
            })
            yield session
        finally:
            if connection:
                try:
                    DevTools(connection).command('Browser.close')
                except (OSError, ValueError, RuntimeError, websocket.WebSocketException):
                    pass
                connection.close()
            if process.poll() is None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def compare(expected, actual, difference, channel_tolerance=24, max_changed_fraction=0.005):
    if expected.size != actual.size:
        raise ValueError(f'Screenshot dimensions differ: {expected.size} != {actual.size}')
    delta = ImageChops.difference(expected.convert('RGB'), actual.convert('RGB'))
    red, green, blue = delta.split()
    largest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    mask = largest.point(lambda value: 255 if value > channel_tolerance else 0)
    changed = mask.histogram()[255]
    total = expected.width * expected.height
    delta.point(lambda value: min(255, value * 4)).save(difference)
    return {
        'passed': changed / total <= max_changed_fraction,
        'changed_pixels': changed, 'total_pixels': total,
        'changed_fraction': changed / total,
        'max_channel_delta': largest.getextrema()[1],
        'channel_tolerance': channel_tolerance,
        'max_changed_fraction': max_changed_fraction,
    }


def check(browser, output, timeout=60, update_baselines=False, no_sandbox=False):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.pop('LD_LIBRARY_PATH', None)
    report = {'viewport': list(VIEWPORT), 'scene': list(SCENE), 'cases': {}}
    baselines = FIXTURES / 'baselines'
    if update_baselines:
        baselines.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='chromium-rendering.') as temporary, \
            serve_page(FIXTURES) as (base, requested):
        directory = Path(temporary)
        version = browser_version(browser, environment, directory, timeout)
        if version != 'Chromium ' + CONFIGURATION['version']:
            raise ValueError('Unexpected rendering browser version: ' + version)
        report['browser'] = version
        flags = [
            '--headless', '--disable-gpu', '--no-first-run',
            '--no-default-browser-check', '--disable-background-networking',
            '--hide-scrollbars', '--force-device-scale-factor=1',
            '--force-color-profile=srgb', '--window-size=800,600',
            '--run-all-compositor-stages-before-draw',
        ]
        if no_sandbox:
            flags.append('--no-sandbox')
        with browser_session(browser, flags, environment, directory, output, timeout) as session:
            for name, expected_boxes in CASES.items():
                result = {'passed': False}
                report['cases'][name] = result
                try:
                    url = base.removesuffix('page.html') + name + '.html'
                    state = session.navigate(url, timeout)
                    screenshot = output / (name + '.actual.png')
                    image = session.command('Page.captureScreenshot', {
                        'format': 'png', 'captureBeyondViewport': False, 'fromSurface': True,
                    })
                    screenshot.write_bytes(base64.b64decode(image['data']))
                    result['page'] = state
                    if (not state.get('ready') or state.get('boxes') != expected_boxes
                            or state.get('viewport') != [*VIEWPORT, 1]):
                        raise ValueError('Fixture did not reach expected layout: ' + str(state))
                    if name == 'graphics' and state.get('pixel') != [43, 139, 207, 255]:
                        raise ValueError('Canvas 2D pixel readback failed')
                    with Image.open(screenshot) as image:
                        if image.size != VIEWPORT:
                            raise ValueError('Unexpected screenshot viewport: ' + str(image.size))
                        actual = image.convert('RGB').crop(SCENE)
                    if max(ImageStat.Stat(actual).stddev) < 20:
                        raise ValueError('Screenshot has no rendered scene')
                    baseline = baselines / (name + '.png')
                    if update_baselines and not baseline.exists():
                        expected = actual.copy()
                    else:
                        with Image.open(baseline) as image:
                            expected = image.convert('RGB')
                    expected.save(output / (name + '.expected.png'))
                    result.update(compare(expected, actual, output / (name + '.diff.png')))
                    if update_baselines:
                        actual.save(baseline)
                        result['previous_baseline_matched'] = result['passed']
                        result['baseline_updated'] = True
                        result['passed'] = True
                    if not result['passed']:
                        result['error'] = 'Screenshot differs from reviewed baseline'
                except (ValueError, OSError, RuntimeError, websocket.WebSocketException) as error:
                    result['error'] = str(error)
        required = {'/layout.html', '/graphics.html', '/page.css', '/page.js', '/mark.svg'}
        report['requested'] = sorted(requested)
        report['passed'] = (all(case['passed'] for case in report['cases'].values())
                            and required.issubset(requested))
    if update_baselines and report['passed']:
        (baselines / 'provenance.json').write_text(json.dumps({
            'browser': report['browser'], 'viewport': list(VIEWPORT),
            'scene': list(SCENE), 'renderer': 'headless software, sRGB, scale factor 1',
        }, indent=2) + '\n')
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    if not report['passed']:
        raise RuntimeError('Rendering checks failed; inspect ' + str(output / 'report.json'))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--executable', default='chrome')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--update-baselines', action='store_true')
    parser.add_argument('--no-sandbox', action='store_true')
    args = parser.parse_args()
    report = check(args.directory.resolve() / args.executable, args.output, args.timeout,
                   args.update_baselines, args.no_sandbox)
    for name, result in report['cases'].items():
        status = 'baseline updated' if result.get('baseline_updated') else 'rendering passed'
        print(f"{name}: {status}, {result['changed_pixels']} changed pixels")


if __name__ == '__main__':
    main()

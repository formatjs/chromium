import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.ci.profile_buildbuddy import trace_summary
from tools.ci.trace_events import TraceEvents


class TraceEventsTest(unittest.TestCase):
    def test_chunk_boundaries_preserve_escaped_strings_unicode_and_numbers(self):
        events = [{'name': 'quote\\" bracket ] snowman \u2603', 'ph': 'X', 'dur': 123456789},
                  {'name': 'second', 'args': {'text': 'traceEvents: [not an array]'}}]
        payload = {'otherData': {'text': '\"traceEvents\": []', 'number': 123456789},
                   'traceEvents': events, 'tail': {'complete': True}}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'trace.json'
            path.write_text(json.dumps(payload, ensure_ascii=False))
            for chunk in [1, 7, 64, 65536]:
                reader = TraceEvents(path, chunk_size=chunk)
                with self.subTest(chunk=chunk):
                    self.assertEqual(list(reader), events)
                    self.assertTrue(reader.complete)

    def test_summary_never_reads_whole_profile_into_one_string(self):
        payload = json.dumps({'traceEvents': [
            {'ph': 'X', 'dur': 20, 'name': 'ignored private details'} for _ in range(4000)]})
        sizes = []

        class BoundedReader(io.BytesIO):
            def read(self, size=-1):
                if size < 0 or size > 65536:
                    raise AssertionError('Unbounded profile read')
                sizes.append(size)
                return super().read(size)

        result = trace_summary(BoundedReader(payload.encode()))
        self.assertGreater(len(sizes), 1)
        self.assertEqual(result['event_count'], 4000)
        self.assertEqual(len(result['longest_events']), 40)
        self.assertTrue(result['trace_complete'])
        self.assertNotIn('private', json.dumps(result))

    def test_interrupted_gzip_retains_only_complete_events_in_diagnostic_mode(self):
        events = [{'ph': 'X', 'dur': index, 'name': 'event' + str(index)} for index in range(100)]
        payload = gzip.compress(json.dumps({'traceEvents': events}).encode())[:-8]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'trace.gz'
            path.write_bytes(payload)
            reader = TraceEvents(path, allow_partial=True, chunk_size=7)
            recovered = list(reader)
            self.assertGreater(len(recovered), 0)
            self.assertEqual(recovered, events[:len(recovered)])
            self.assertFalse(reader.complete)
            with self.assertRaises(json.JSONDecodeError):
                list(TraceEvents(path, chunk_size=7))


if __name__ == '__main__':
    unittest.main()

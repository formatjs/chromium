"""Read complete or interrupted Bazel traces without loading their JSON tree."""

import gzip
import io
import json
from contextlib import ExitStack


class TraceEvents:
    def __init__(self, path, allow_partial=False, chunk_size=65536):
        self.path = path
        self.allow_partial = allow_partial
        self.chunk_size = chunk_size
        self.complete = False

    def __iter__(self):
        self.complete = False
        count = 0
        with ExitStack() as resources:
            source = self.path if hasattr(self.path, 'read') else resources.enter_context(self.path.open('rb'))
            prefix = source.read(2)
            buffered = resources.enter_context(io.BufferedReader(_PrefixReader(prefix, source)))
            binary = gzip.GzipFile(fileobj=buffered) if prefix == b'\x1f\x8b' else buffered
            text = resources.enter_context(io.TextIOWrapper(binary, encoding='utf-8'))
            stream = _JsonStream(text, self.chunk_size)
            try:
                stream.expect('{')
                found = False
                if stream.peek() != '}':
                    while True:
                        key = stream.value()
                        if not isinstance(key, str):
                            stream.error('Expected profile property name')
                        stream.expect(':')
                        if key == 'traceEvents':
                            if found:
                                stream.error('Duplicate traceEvents array')
                            found = True
                            stream.expect('[')
                            if stream.peek() != ']':
                                while True:
                                    event = stream.value()
                                    if not isinstance(event, dict):
                                        raise ValueError('Profile event must be an object')
                                    count += 1
                                    yield event
                                    if stream.peek() == ']':
                                        break
                                    stream.expect(',')
                            stream.expect(']')
                        else:
                            stream.value()
                        if stream.peek() == '}':
                            break
                        stream.expect(',')
                stream.expect('}')
                if stream.peek() or stream.interrupted:
                    stream.error('Incomplete profile or trailing data')
                self.complete = True
            except json.JSONDecodeError:
                if not self.allow_partial:
                    raise
                if not count:
                    raise ValueError('Partial profile has no complete events') from None


class _PrefixReader(io.RawIOBase):
    def __init__(self, prefix, source):
        self.prefix = prefix
        self.source = source

    def readable(self):
        return True

    def readinto(self, target):
        count = min(len(target), len(self.prefix))
        target[:count] = self.prefix[:count]
        self.prefix = self.prefix[count:]
        if count < len(target):
            data = self.source.read(len(target) - count)
            target[count:count + len(data)] = data
            count += len(data)
        return count


class _JsonStream:
    def __init__(self, source, chunk_size):
        self.source = source
        self.chunk_size = chunk_size
        self.buffer = ''
        self.position = 0
        self.eof = False
        self.interrupted = False
        self.decoder = json.JSONDecoder()

    def more(self):
        self.buffer = self.buffer[self.position:]
        self.position = 0
        try:
            chunk = self.source.read(self.chunk_size)
        except (EOFError, UnicodeDecodeError):
            chunk = ''
            self.interrupted = True
        self.eof = not chunk
        self.buffer += chunk
        if len(self.buffer) > 16 * 1024 * 1024:
            raise ValueError('Profile JSON value exceeds 16 MiB')

    def error(self, message):
        raise json.JSONDecodeError(message, self.buffer, self.position)

    def peek(self):
        while True:
            while self.position < len(self.buffer) and self.buffer[self.position].isspace():
                self.position += 1
            if self.position < len(self.buffer):
                return self.buffer[self.position]
            if self.eof:
                return ''
            self.more()

    def expect(self, token):
        if self.peek() != token:
            self.error('Expected ' + token)
        self.position += 1

    def value(self):
        self.peek()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.position)
            except json.JSONDecodeError:
                if self.eof:
                    raise
                self.more()
                continue
            if end == len(self.buffer) and not self.eof:
                self.more()
                continue
            self.position = end
            return value

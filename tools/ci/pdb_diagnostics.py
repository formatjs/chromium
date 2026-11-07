"""Hash MSF streams to locate PDB variation; never relax artifact equality."""

import hashlib
import re
import struct
import tempfile


def summarize(source, size):
    with tempfile.TemporaryFile() as storage:
        digest = hashlib.sha256()
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            storage.write(chunk)
        if storage.tell() != size:
            raise ValueError('Truncated PDB')
        storage.seek(0)
        header = storage.read(56)
        if len(header) != 56 or header[:32] != b'Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0':
            raise ValueError('Invalid MSF header')
        page_size, _, pages, directory_size, _, map_page = struct.unpack_from('<6I', header, 32)
        if page_size not in (512, 1024, 2048, 4096, 8192, 16384, 32768, 65536) or pages * page_size != size:
            raise ValueError('Invalid MSF page layout')
        if directory_size > 64 * 1024 * 1024:
            raise ValueError('MSF directory exceeds 64 MiB')

        def read_at(position, length):
            if position < 0 or position + length > size:
                raise ValueError('MSF range outside file')
            storage.seek(position)
            return storage.read(length)

        def chunks(indices, length):
            for index in indices:
                if index >= pages:
                    raise ValueError('Invalid MSF page index')
                amount = min(length, page_size)
                yield read_at(index * page_size, amount)
                length -= amount
            if length:
                raise ValueError('Incomplete MSF stream')

        count = (directory_size + page_size - 1) // page_size
        directory_pages = struct.unpack('<' + str(count) + 'I', read_at(map_page * page_size, count * 4))
        directory = b''.join(chunks(directory_pages, directory_size))
        if len(directory) < 4:
            raise ValueError('Missing MSF stream directory')
        streams = struct.unpack_from('<I', directory)[0]
        if streams > 200000 or 4 + streams * 4 > len(directory):
            raise ValueError('Invalid MSF stream count')
        lengths = struct.unpack_from('<' + str(streams) + 'I', directory, 4)
        position, mappings, result = 4 + streams * 4, {}, {}
        for index, length in enumerate(lengths):
            if length == 0xffffffff:
                continue
            count = (length + page_size - 1) // page_size
            if position + count * 4 > len(directory):
                raise ValueError('Incomplete MSF page map')
            indices = struct.unpack_from('<' + str(count) + 'I', directory, position)
            position += count * 4
            mappings[index] = (indices, length)
            stream_hash = hashlib.sha256()
            for chunk in chunks(indices, length):
                stream_hash.update(chunk)
            result[str(index)] = {'size': length, 'sha256': stream_hash.hexdigest()}
        if 3 in mappings:
            indices, length = mappings[3]
            if length >= 64:
                header = read_at(indices[0] * page_size, 64)
                position, end = 64, 64 + struct.unpack_from('<I', header, 24)[0]
                if end > length or end > 64 * 1024 * 1024:
                    raise ValueError('Invalid DBI module bounds')
                dbi = b''.join(chunks(indices[:(end + page_size - 1) // page_size], end))
                while position + 64 <= end:
                    index = struct.unpack_from('<H', dbi, position + 34)[0]
                    name_end = dbi.find(b'\0', position + 64, end)
                    object_end = dbi.find(b'\0', name_end + 1, end)
                    if name_end < 0 or object_end < 0:
                        raise ValueError('Invalid DBI module names')
                    name = dbi[position + 64:name_end].decode('utf-8', errors='replace')
                    if str(index) in result:
                        result[str(index)]['module'] = name
                        if name == '* Linker *' and mappings[index][1] <= 1024 * 1024:
                            data = b''.join(chunks(*mappings[index]))
                            result[str(index)]['environment_paths'] = {
                                key: match.group(1).decode('utf-8', errors='replace')
                                for key in ('cwd', 'exe', 'pdb')
                                if (match := re.search(key.encode() + b'\0([^\0]{0,4096})\0', data))}
                    position = (object_end + 4) & ~3
        return {'sha256': digest.hexdigest(), 'page_size': page_size, 'streams': result}

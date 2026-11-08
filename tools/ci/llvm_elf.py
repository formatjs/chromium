"""Verify a metadata-only LLVM relink before BOLT instrumentation."""

import hashlib
from pathlib import Path
import struct


def allocated_sections(path):
    path = Path(path)
    size = path.stat().st_size
    with path.open('rb') as source:
        def read(offset, length):
            if offset < 0 or length < 0 or offset + length > size:
                raise ValueError('ELF range outside file')
            source.seek(offset)
            data = source.read(length)
            if len(data) != length:
                raise ValueError('Truncated ELF file')
            return data

        header = struct.unpack('<16sHHIQQQIHHHHHH', read(0, 64))
        if (header[0][:7] != b'\x7fELF\x02\x01\x01' or header[1] not in (2, 3)
                or header[2] != 62 or header[3] != 1 or header[8] != 64
                or header[9] != 56 or header[11] != 64
                or not 0 < header[10] < 256 or not 0 < header[12] < 65535
                or not 0 < header[13] < header[12]):
            raise ValueError('Expected ordinary x86-64 little-endian ELF executable')
        sections = [struct.unpack('<IIQQQQIIQQ', read(header[6] + i * 64, 64))
                    for i in range(header[12])]
        names_section = sections[header[13]]
        if names_section[1] != 3 or names_section[5] > 4 * 1024 * 1024:
            raise ValueError('Unexpected ELF section name table')
        names = read(names_section[4], names_section[5])
        result, notes, relocations = {}, {}, []
        ignored = [(40, 48), (60, 64)]  # Section table location/count, not loaded program behavior.
        all_names = []
        for row in sections:
            if row[0] >= len(names) or names.find(b'\0', row[0]) < 0:
                raise ValueError('Invalid ELF section name')
            all_names.append(names[row[0]:names.index(b'\0', row[0])].decode('ascii'))
        for name, row in zip(all_names, sections):
            if row[1] in (4, 9) and row[7] < len(sections) and all_names[row[7]] == '.text':
                relocations.append(name)
            if not row[2] & 2:
                continue
            if name in result:
                raise ValueError('Duplicate allocated ELF section')
            entry = {'type': row[1], 'flags': row[2], 'address': row[3],
                     'offset': row[4], 'bytes': row[5], 'alignment': row[8], 'entry_size': row[9]}
            digest = None
            if row[1] != 8:
                hasher = hashlib.sha256()
                for offset in range(0, row[5], 65536):
                    hasher.update(read(row[4] + offset, min(65536, row[5] - offset)))
                digest = hasher.hexdigest()
            if name == '.note.gnu.build-id':
                if row[1] != 7:
                    raise ValueError('Build ID is not an ELF note')
                name_size, descriptor_size, note_type = struct.unpack('<III', read(row[4], 12))
                descriptor = 12 + (name_size + 3) // 4 * 4
                if (name_size != 4 or note_type != 3 or not 0 < descriptor_size <= 64
                        or descriptor + descriptor_size > row[5] or read(row[4] + 12, 4) != b'GNU\0'):
                    raise ValueError('Unexpected GNU build ID note')
                ignored.append((row[4] + descriptor, row[4] + descriptor + descriptor_size))
                notes[name] = digest
                note = bytearray(read(row[4], row[5]))
                note[descriptor:descriptor + descriptor_size] = bytes(descriptor_size)
                digest = hashlib.sha256(note).hexdigest()
            entry['sha256'] = digest
            result[name] = entry
        loads = [struct.unpack('<IIQQQQQQ', read(header[5] + i * 56, 56))
                 for i in range(header[10])]
        loads = [row for row in loads if row[0] == 1]
        if '.text' not in result or not result['.text']['bytes'] or not loads:
            raise ValueError('ELF executable lacks loaded code')
        images = []
        for row in loads:
            hasher = hashlib.sha256()
            for offset in range(row[2], row[2] + row[5], 65536):
                chunk = bytearray(read(offset, min(65536, row[2] + row[5] - offset)))
                for start, end in ignored:
                    left, right = max(start, offset), min(end, offset + len(chunk))
                    if left < right:
                        chunk[left - offset:right - offset] = bytes(right - left)
                hasher.update(chunk)
            images.append(hasher.hexdigest())
        return {'entry': header[4], 'load_segments': loads, 'sections': result,
                'mapped_image_sha256': images,
                'build_id_notes': notes, 'symbol_table_present': any(row[1] == 2 for row in sections),
                'text_relocation_sections': relocations}


def compare_relinked_compiler(reference, candidate):
    before, after = allocated_sections(reference), allocated_sections(candidate)
    for key in ['entry', 'load_segments', 'sections', 'mapped_image_sha256']:
        if before[key] != after[key]:
            raise ValueError('Compiler loaded code/data changed during relocation relink: ' + key)
    return {'loaded_code_data_bytes_match': True, 'load_layout_matches': True,
            'allocated_section_count': len(before['sections']),
            'build_id_changed': before['build_id_notes'] != after['build_id_notes'],
            'symbol_table_present': after['symbol_table_present'],
            'text_relocation_sections': after['text_relocation_sections']}

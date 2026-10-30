"""Recover absolute ARM64 export tables without depending on kallsyms _text."""
import collections
import re
import struct


def exported(image, expected):
    assert image[56:60] == b'ARMd' and len(image) < 128*1024*1024
    seed = b'remap_pfn_range\0'
    names = [match.start() for match in re.finditer(re.escape(seed), image)]
    assert names, 'No literal exported remap_pfn_range string'
    residues = collections.defaultdict(list)
    for off in names:
        residues[off & 4095].append(off)
    candidates = {}
    for index, (pointer,) in enumerate(struct.iter_unpack('<Q', image[:len(image)//8*8])):
        if pointer >> 48 != 0xffff or pointer & 4095 not in residues or index == 0:
            continue
        for off in residues[pointer & 4095]:
            base = pointer-off
            if base >> 48 != 0xffff or base & 4095:
                continue
            position = index*8-8
            function = struct.unpack_from('<Q', image, position)[0]
            if not base <= function < base+128*1024*1024:
                continue

            def entry(pos):
                if pos < 0 or pos+16 > len(image):
                    return None
                address, name = struct.unpack_from('<QQ', image, pos)
                relative = name-base
                if not base <= address < base+128*1024*1024 or not 0 <= relative < len(image):
                    return None
                text = image[relative:relative+256].split(b'\0', 1)[0]
                return text.decode() if re.fullmatch(rb'[A-Za-z_][A-Za-z0-9_.$]*', text) else None

            if entry(position) != 'remap_pfn_range':
                continue
            begin = position
            while entry(begin-16):
                begin -= 16
            rows = []
            end = begin
            while name := entry(end):
                rows.append(name)
                end += 16
            if len(rows) > 1000 and len(rows) == len(set(rows)):
                candidates[(base, begin, end)] = rows
    assert len(candidates) == 1, ('Ambiguous or unsupported absolute export table', len(candidates))
    (base, begin, end), rows = next(iter(candidates.items()))
    groups = []
    for name in rows:
        if not groups or name <= groups[-1][-1]:
            groups.append([])
        groups[-1].append(name)
    wanted = set(expected.values())-{0, 0xffffffff}
    positions = collections.defaultdict(list)
    for index, (value,) in enumerate(struct.iter_unpack('<I', image[:len(image)//4*4])):
        if value in wanted:
            positions[value].append(index*4)
    values, proof = {}, []
    for group in groups:
        votes = collections.Counter()
        for index, name in enumerate(group):
            if name in expected and expected[name] in wanted:
                for position in positions[expected[name]]:
                    votes[position-index*4] += 1
        assert votes, 'No independent direct export CRC votes'
        ranked = votes.most_common(2)
        crc_start, count = ranked[0]
        assert count >= 10 and (len(ranked) == 1 or count > ranked[1][1])
        assert 0 <= crc_start and crc_start+4*len(group) <= len(image)
        for index, name in enumerate(group):
            values[name] = struct.unpack_from('<I', image, crc_start+index*4)[0]
        proof.append({'first': group[0], 'last': group[-1], 'exports': len(group),
                      'independent_crc_votes': count})
    common = set(expected) & set(values)
    return {'parser': 'absolute_export_pointer_geometry_unique_base_and_unique_CRC_votes',
            'export_table_file_start': begin, 'export_table_file_end': end,
            'exports_recovered': len(values), 'shared_exports_compared': len(common),
            'different_export_crcs': [{'name': name, 'candidate': f'{expected[name]:08x}',
                                       'firmware': f'{values[name]:08x}'}
                                      for name in sorted(common) if expected[name] != values[name]],
            'candidate_exports_missing_from_firmware': sorted(set(expected)-set(values)),
            'firmware_exports_missing_from_candidate': sorted(set(values)-set(expected)),
            'table_location_proof': proof}

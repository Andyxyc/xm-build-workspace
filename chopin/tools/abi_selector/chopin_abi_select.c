/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Identify one of two evidenced chopin vendor ABI families from real
 * AArch64 ELF module __versions records. No device operations or privilege
 * changes. Unknown signatures are errors, never a guessed compatibility.
 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

enum result_code {
    RESULT_OK = 0,
    RESULT_USAGE = 2,
    RESULT_IO = 3,
    RESULT_ELF = 4,
    RESULT_VERSIONS = 5,
    RESULT_UNKNOWN = 6,
    RESULT_MIXED = 7,
    RESULT_INCOMPLETE = 8
};

enum { ELF_HEADER_BYTES = 64, ELF_SECTION_BYTES = 64, VERSION_BYTES = 64 };
#define FILE_LIMIT (64u * 1024u * 1024u)
#define VERSION_LIMIT (1024u * 1024u)
#define SECTION_LIMIT 16384u
#define SECTION_NAME_LIMIT 256u
#define INPUT_LIMIT 32
#define FAMILY_LEGACY 1u
#define FAMILY_T 2u
#define REQUIRED_ANCHORS 7u

struct anchor {
    const char *name;
    uint32_t legacy_crc;
    uint32_t t_crc;
};
static const struct anchor anchors[] = {
    { "cpu_hwcaps", UINT32_C(0xbe9f1a32), UINT32_C(0xf2352f28) },
    { "cpu_hwcap_keys", UINT32_C(0x77af701b), UINT32_C(0x37c71621) },
    { "remap_pfn_range", UINT32_C(0xf79cd398), UINT32_C(0x5cf0b028) },
    { "find_vma", UINT32_C(0x30e3495c), UINT32_C(0x40a015a7) }
};
struct evidence {
    unsigned family;
    unsigned seen;
};

static uint16_t le16(const unsigned char *p)
{
    return (uint16_t)((uint16_t)p[0] | (uint16_t)p[1] << 8);
}
static uint32_t le32(const unsigned char *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
           (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static uint64_t le64(const unsigned char *p)
{
    return (uint64_t)le32(p) | (uint64_t)le32(p + 4) << 32;
}
static int in_file(uint64_t offset, uint64_t bytes, size_t length)
{
    return offset <= (uint64_t)length && bytes <= (uint64_t)length - offset;
}
static int fail(int code, const char *message)
{
    fprintf(stderr, "ABI selection: %s\n", message);
    return code;
}
static int symbol_name(const unsigned char *p, size_t bytes)
{
    size_t i;
    if (!bytes || !((p[0] >= 'A' && p[0] <= 'Z') ||
                    (p[0] >= 'a' && p[0] <= 'z') || p[0] == '_'))
        return 0;
    for (i = 1; i < bytes; ++i) {
        unsigned char c = p[i];
        if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
              (c >= '0' && c <= '9') || c == '_' || c == '.' || c == '$'))
            return 0;
    }
    return 1;
}

static int parse_module(const unsigned char *data, size_t length,
                        struct evidence *evidence)
{
    uint64_t section_offset, strings_offset, strings_bytes;
    uint64_t versions_offset = 0, versions_bytes = 0;
    uint16_t section_count, strings_index;
    unsigned versions_sections = 0;
    size_t i;
    const unsigned char *strings;

    if (length < ELF_HEADER_BYTES || memcmp(data, "\177ELF", 4) ||
        data[4] != 2 || data[5] != 1 || data[6] != 1 ||
        le16(data + 16) != 1 || le16(data + 18) != 183 ||
        le32(data + 20) != 1 || le16(data + 52) != ELF_HEADER_BYTES ||
        le16(data + 58) != ELF_SECTION_BYTES)
        return fail(RESULT_ELF, "expected ELF64 little-endian AArch64 ET_REL module");

    section_offset = le64(data + 40);
    section_count = le16(data + 60);
    strings_index = le16(data + 62);
    if (!section_count || section_count > SECTION_LIMIT ||
        !strings_index || strings_index >= section_count ||
        section_offset < ELF_HEADER_BYTES ||
        !in_file(section_offset, (uint64_t)section_count * ELF_SECTION_BYTES, length))
        return fail(RESULT_ELF, "invalid or unsupported ELF section table");
    {
        const unsigned char *h = data + (size_t)section_offset +
                                 (size_t)strings_index * ELF_SECTION_BYTES;
        if (le32(h + 4) != 3)
            return fail(RESULT_ELF, "invalid section-name string table");
        strings_offset = le64(h + 24);
        strings_bytes = le64(h + 32);
        if (!strings_bytes || !in_file(strings_offset, strings_bytes, length))
            return fail(RESULT_ELF, "truncated section-name string table");
        strings = data + (size_t)strings_offset;
    }

    for (i = 0; i < section_count; ++i) {
        const unsigned char *h = data + (size_t)section_offset + i * ELF_SECTION_BYTES;
        uint32_t name_offset = le32(h), kind = le32(h + 4);
        uint64_t offset = le64(h + 24), bytes = le64(h + 32);
        const unsigned char *name, *terminator;
        if (name_offset >= strings_bytes)
            return fail(RESULT_ELF, "section name is outside its string table");
        name = strings + name_offset;
        {
            uint64_t available = strings_bytes - name_offset;
            size_t limit = available < SECTION_NAME_LIMIT ?
                           (size_t)available : SECTION_NAME_LIMIT;
            terminator = memchr(name, 0, limit);
        }
        if (!terminator)
            return fail(RESULT_ELF, "unterminated section name");
        /* NOBITS has no file payload. Other sections must fit the file. */
        if (kind != 8 && !in_file(offset, bytes, length))
            return fail(RESULT_ELF, "section payload exceeds module file");
        if ((size_t)(terminator - name) != sizeof("__versions") - 1 ||
            memcmp(name, "__versions", sizeof("__versions") - 1))
            continue;
        ++versions_sections;
        if (versions_sections != 1 || kind != 1 ||
            (le64(h + 56) != 0 && le64(h + 56) != VERSION_BYTES))
            return fail(RESULT_VERSIONS, "invalid or duplicate __versions section");
        versions_offset = offset;
        versions_bytes = bytes;
    }
    if (versions_sections != 1 || !versions_bytes ||
        versions_bytes > VERSION_LIMIT || versions_bytes % VERSION_BYTES)
        return fail(RESULT_VERSIONS, "missing or malformed 64-byte __versions records");

    for (i = 0; i < (size_t)versions_bytes; i += VERSION_BYTES) {
        const unsigned char *record = data + (size_t)versions_offset + i;
        const unsigned char *name = record + 8;
        const unsigned char *end = memchr(name, 0, VERSION_BYTES - 8);
        uint64_t crc = le64(record);
        size_t n;
        if (!end || !symbol_name(name, (size_t)(end - name)) || crc > UINT32_MAX)
            return fail(RESULT_VERSIONS, "invalid symbol or CRC in __versions record");
        for (n = 0; n < sizeof(anchors) / sizeof(anchors[0]); ++n) {
            unsigned family;
            if (strcmp((const char *)name, anchors[n].name))
                continue;
            if ((uint32_t)crc == anchors[n].legacy_crc)
                family = FAMILY_LEGACY;
            else if ((uint32_t)crc == anchors[n].t_crc)
                family = FAMILY_T;
            else {
                fprintf(stderr, "ABI selection: unsupported %s CRC 0x%08" PRIx32 "\n",
                        anchors[n].name, (uint32_t)crc);
                return RESULT_UNKNOWN;
            }
            evidence->family |= family;
            evidence->seen |= 1u << n;
            if (evidence->family == (FAMILY_LEGACY | FAMILY_T))
                return fail(RESULT_MIXED, "conflicting vendor ABI families");
        }
    }
    return RESULT_OK;
}

static int read_module(const char *path, struct evidence *evidence)
{
    struct stat st;
    unsigned char *data;
    size_t length, received = 0;
    int fd, result;
    /* NONBLOCK prevents a supplied FIFO from blocking before fstat rejects it.
     * A symlink to a regular module is allowed; no special-file data is read. */
    fd = open(path, O_RDONLY | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0)
        return fail(RESULT_IO, "cannot open module file");
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) ||
        st.st_size < ELF_HEADER_BYTES || (uint64_t)st.st_size > FILE_LIMIT) {
        close(fd);
        return fail(RESULT_IO, "input must be a bounded regular module file");
    }
    length = (size_t)st.st_size;
    data = malloc(length);
    if (!data) {
        close(fd);
        return fail(RESULT_IO, "cannot allocate module buffer");
    }
    while (received < length) {
        ssize_t amount = read(fd, data + received, length - received);
        if (amount < 0 && errno == EINTR)
            continue;
        if (amount <= 0) {
            free(data);
            close(fd);
            return fail(RESULT_IO, "module read failed or file changed during read");
        }
        received += (size_t)amount;
    }
    if (close(fd)) {
        free(data);
        return fail(RESULT_IO, "module file close failed");
    }
    result = parse_module(data, length, evidence);
    free(data);
    return result;
}

int main(int argc, char **argv)
{
    struct evidence evidence = { 0, 0 };
    int i;
    if (argc == 2 && !strcmp(argv[1], "--help")) {
        puts("Usage: chopin-abi-select MODULE.ko [MODULE.ko ...]");
        puts("Success: stdout is legacy or t. Errors are on stderr.");
        puts("Exit codes: 2 usage; 3 file; 4 ELF; 5 versions; 6 unknown; 7 mixed; 8 incomplete.");
        return RESULT_OK;
    }
    if (argc < 2 || argc > INPUT_LIMIT + 1)
        return fail(RESULT_USAGE, "supply one to thirty-two vendor module files");
    for (i = 1; i < argc; ++i) {
        int result = read_module(argv[i], &evidence);
        if (result)
            return result;
    }
    if ((evidence.seen & REQUIRED_ANCHORS) != REQUIRED_ANCHORS)
        return fail(RESULT_INCOMPLETE, "cpu_hwcaps, cpu_hwcap_keys and remap_pfn_range are required");
    if (evidence.family == FAMILY_LEGACY)
        puts("legacy");
    else if (evidence.family == FAMILY_T)
        puts("t");
    else
        return fail(RESULT_INCOMPLETE, "no supported vendor ABI evidence");
    return RESULT_OK;
}

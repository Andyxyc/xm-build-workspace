"""Bounded, in-memory kheaders.ko -> selected generated-header evidence only.
No network, filesystem extraction, module execution/load, or output of full OEM bytes.
Source layout: MiCode chopin-r-oss 2af31af37e12a338fddca780044f8b182c23ed9a.
ELF checks follow the reviewed vendor_reader.parse_module approach, with exact
kernel_headers_data/_end anchors. Missing anchors fail; no magic-byte search.
"""
import hashlib,lzma,re,struct,posixpath

class KheadersError(ValueError):pass

def need(ok,message):
    if not ok:raise KheadersError(message)

HARD_LIMITS={'module':4*1024*1024,'xz':4*1024*1024,'xz_memory':64*1024*1024,
 'raw_tar':96*1024*1024,'sections':4096,'symbols':16384,'members':32768,
 'member':2*1024*1024,'path':512,'macros':128,'value':256,'links':4096}
SELECTED_HEADERS={
 'include/generated/autoconf.h':'config',
 'include/generated/utsrelease.h':'release',
 'include/generated/uapi/linux/version.h':'version',
 'include/linux/version.h':'version',
 'include/generated/compile.h':'digest_only',
 'include/generated/utsversion.h':'digest_only'}
DEFAULT_MACROS=('CONFIG_ARM64','CONFIG_SMP','CONFIG_PREEMPT','CONFIG_MODVERSIONS',
 'CONFIG_IKCONFIG','CONFIG_IKCONFIG_PROC','CONFIG_IKHEADERS','CONFIG_IKHEADERS_MODULE',
 'CONFIG_BLK_INLINE_ENCRYPTION','CONFIG_DM_DEFAULT_KEY','CONFIG_FS_ENCRYPTION',
 'CONFIG_MTK_CHARGER','CONFIG_MTK_BATTERY','CONFIG_MTK_ECCCI_DRIVER')

def limits_for(overrides):
    out=HARD_LIMITS.copy()
    for k,v in (overrides or {}).items():
        need(k in out and type(v) is int and 1<=v<=out[k],'Limits may only be lowered within hard caps')
        out[k]=v
    return out

def cstring(table,offset,label):
    need(0<=offset<len(table),label+' string offset')
    end=table.find(b'\0',offset);need(end>=0,label+' unterminated string')
    try:return table[offset:end].decode('ascii')
    except UnicodeError:raise KheadersError(label+' non-ASCII string')

def archive_from_elf(data,L):
    need(type(data) is bytes and 64<=len(data)<=L['module'],'Module byte/type bound')
    need(data[:7]==b'\x7fELF\x02\x01\x01','ELF64 little-endian version1 required')
    need(struct.unpack_from('<HHI',data,16)==(1,183,1),'ARM64 ET_REL required')
    shoff=struct.unpack_from('<Q',data,40)[0];ents,count,strings=struct.unpack_from('<HHH',data,58)
    need(ents==64 and 0<count<=L['sections'] and strings<count and shoff>=64 and shoff+64*count<=len(data),'ELF section table bound')
    sections=[struct.unpack_from('<IIQQQQIIQQ',data,shoff+64*i) for i in range(count)]
    for s in sections:need(s[1]==8 or s[4]+s[5]<=len(data),'ELF section outside module')
    names=sections[strings];need(names[1]==3,'ELF shstrtab missing');names=data[names[4]:names[4]+names[5]]
    snames=[cstring(names,s[0],'section') for s in sections]
    need(len(set(snames[1:]))==len(snames)-1,'Duplicate section names')
    anchors={'kernel_headers_data':[],'kernel_headers_data_end':[]};total=0
    for s in sections:
        if s[1]!=2:continue
        need(s[9]==24 and s[5]%24==0 and s[6]<count and sections[s[6]][1]==3,'Invalid ELF symtab')
        total+=s[5]//24;need(total<=L['symbols'],'ELF symbol count bound')
        st=sections[s[6]];text=data[st[4]:st[4]+st[5]]
        for p in range(s[4],s[4]+s[5],24):
            name,info,other,ndx,value,size=struct.unpack_from('<IBBHQQ',data,p)
            key=cstring(text,name,'symbol')
            if key in anchors:
                need(info>>4==1 and info&15==0,'Header anchors must be global STT_NOTYPE')
                anchors[key].append((ndx,value))
    need(all(len(v)==1 for v in anchors.values()),'Unique header start/end symbols required')
    (a,start),(b,end)=anchors['kernel_headers_data'][0],anchors['kernel_headers_data_end'][0]
    need(a==b and 0<a<count,'Header anchors differ in section')
    sec=sections[a]
    need(sec[1]==1 and sec[2]&2 and snames[a]=='.rodata','Header anchors must be in allocated .rodata')
    need(0<=start<end<=sec[5] and end-start<=L['xz'],'Header archive symbol range bound')
    offset=sec[4]+start;archive=data[offset:sec[4]+end]
    need(archive.startswith(b'\xfd7zXZ\x00'),'Anchored archive is not XZ')
    return archive,{'section':snames[a],'section_index':a,'module_file_offset':offset,'compressed_bytes':len(archive),'start_symbol_value':start,'end_symbol_value':end}

def bounded_xz(archive,L):
    try:
        dec=lzma.LZMADecompressor(format=lzma.FORMAT_XZ,memlimit=L['xz_memory'])
        out=bytearray();inp=archive
        while True:
            part=dec.decompress(inp,max_length=L['raw_tar']+1-len(out));out.extend(part);inp=b''
            need(len(out)<=L['raw_tar'],'XZ output bound')
            if dec.eof:
                need(not dec.unused_data,'XZ trailing or concatenated stream rejected');break
            need(not dec.needs_input,'XZ truncated stream')
        return bytes(out)
    except lzma.LZMAError as e:raise KheadersError('XZ decoder rejected: '+str(e))

def field(h,start,size):
    data=h[start:start+size];head,sep,tail=data.partition(b'\0')
    need(not sep or not any(tail),'Tar string has nonzero bytes after NUL')
    try:return head.decode('ascii')
    except UnicodeError:raise KheadersError('Tar non-ASCII field')

def number(b):
    need(not b or not b[0]&128,'Tar base256 numeric form rejected')
    b=b.strip(b'\0 ');need(not b or all(48<=v<=55 for v in b),'Tar non-octal number')
    return int(b,8) if b else 0

def safe_name(name,L,allow_root=False):
    need(len(name.encode('ascii'))<=L['path'] and '\\' not in name and not name.startswith('/'),'Tar path length/absolute/backslash')
    while name.startswith('./'):name=name[2:]
    name=name.rstrip('/')
    if name in ('','.'):need(allow_root,'Tar root name not allowed');return '.'
    parts=name.split('/')
    need(all(p not in ('','..','.') for p in parts) and all(re.fullmatch(r'[A-Za-z0-9_.+@-]+',p) for p in parts),'Tar traversal or unsupported path characters: '+repr(name[:512]))
    return name

def safe_link(member,target,hard,L):
    need(len(target.encode('ascii'))<=L['path'] and target and not target.startswith('/') and '\\' not in target,'Unsafe tar link target')
    norm=posixpath.normpath(target if hard else posixpath.join(posixpath.dirname(member),target))
    need(norm not in ('','..') and not norm.startswith('../'),'Tar link escapes archive root')
    return safe_name(norm,L)

def selected_tar_members(raw,L):
    need(len(raw)%512==0,'Tar block alignment')
    selected={};seen=set();links=[];pos=0;count=0;types={};long_name=None;long_link=None;ended=False
    while pos+512<=len(raw):
        h=raw[pos:pos+512];pos+=512
        if not any(h):
            need(pos+512<=len(raw) and not any(raw[pos:pos+512]) and not any(raw[pos+512:]),'Tar terminal zero blocks/tail')
            need(long_name is None and long_link is None,'Dangling GNU long-name/link record');ended=True;break
        count+=1;need(count<=L['members'],'Tar member count bound')
        expected=number(h[148:156]);need(sum(h[:148])+8*32+sum(h[156:])==expected,'Tar checksum')
        magic=h[257:263];need(magic in (b'ustar\0',b'ustar '),'USTAR/GNU tar required')
        kind=h[156:157];size=number(h[124:136]);need(size<=L['member'],'Tar member size bound')
        end=pos+size;nextpos=(end+511)&~511;need(nextpos<=len(raw),'Tar member exceeds archive')
        payload=raw[pos:end];pos=nextpos;types[kind.decode('ascii') if kind!=b'\0' else 'NUL']=types.get(kind.decode('ascii') if kind!=b'\0' else 'NUL',0)+1
        name=field(h,0,100)
        if magic==b'ustar\0':
            prefix=field(h,345,155)
            if prefix:name=prefix+'/'+name
        if kind in (b'L',b'K'):
            need(name in ('././@LongLink','@LongLink') and 0<size<=L['path']+1 and payload.endswith(b'\0') and b'\0' not in payload[:-1],'Invalid GNU long-name metadata')
            try:value=payload[:-1].decode('ascii')
            except UnicodeError:raise KheadersError('Non-ASCII GNU long name')
            if kind==b'L':need(long_name is None,'Duplicate pending long name');long_name=value
            else:need(long_link is None,'Duplicate pending long link');long_link=value
            continue
        name=safe_name(long_name if long_name is not None else name,L,kind==b'5');long_name=None
        target=long_link if long_link is not None else field(h,157,100);long_link=None
        need(name not in seen,'Duplicate normalized tar member');seen.add(name)
        need(kind in (b'0',b'\0',b'5',b'1',b'2'),'Unsupported tar type (PAX/device/FIFO etc.)')
        if kind==b'5':need(size==0,'Nonempty tar directory')
        elif kind in (b'1',b'2'):
            need(size==0 and name not in SELECTED_HEADERS,'Selected header must not be a link')
            links.append((name,safe_link(name,target,kind==b'1',L)));need(len(links)<=L['links'],'Tar link count bound')
        elif name in SELECTED_HEADERS:
            need(0<size<=L['member'],'Selected header byte bound');selected[name]=payload
    need(ended,'Tar lacks terminal blocks')
    # Links are never followed. Require their lexical targets to exist in archive.
    need(all(target in seen for _,target in links),'Tar link target is absent')
    return selected,{'member_records_including_GNU_metadata':count,'normalized_members':len(seen),'type_counts':types,'links_ignored_without_following':len(links)}

def macro_values(data,names,L):
    try:text=data.decode('ascii')
    except UnicodeError:raise KheadersError('Selected macro header is not ASCII')
    found={}
    for line in text.splitlines():
        m=re.fullmatch(r'\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.*?)\s*',line)
        if m and m[1] in names:
            need(m[1] not in found and len(m[2])<=L['value'] and all(32<=ord(c)<127 for c in m[2]),'Duplicate/oversized requested macro')
            found[m[1]]=m[2]
    return {name:({'state':'defined','value':found[name]} if name in found else {'state':'not_defined_in_this_header'}) for name in names}

def inspect_kheaders_module(name,data,macro_names=DEFAULT_MACROS,limit_overrides=None):
    need(name=='kheaders.ko','Only exact kheaders.ko intake allowed')
    L=limits_for(limit_overrides);macro_names=tuple(macro_names)
    need(len(macro_names)<=L['macros'] and len(set(macro_names))==len(macro_names) and all(type(x) is str and re.fullmatch(r'CONFIG_[A-Za-z0-9_]{1,100}',x) for x in macro_names),'Requested CONFIG macro allowlist bound')
    archive,bounds=archive_from_elf(data,L);raw=bounded_xz(archive,L);selected,tar_meta=selected_tar_members(raw,L);headers={}
    for path,payload in selected.items():
        kind=SELECTED_HEADERS[path];entry={'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
        if kind=='config':entry['requested_macros']=macro_values(payload,macro_names,L)
        elif kind=='release':entry['requested_macros']=macro_values(payload,('UTS_RELEASE',),L)
        elif kind=='version':entry['requested_macros']=macro_values(payload,('LINUX_VERSION_CODE',),L)
        headers[path]=entry
    return {'status':'BOUNDED_GENERATED_HEADER_EVIDENCE' if 'include/generated/autoconf.h' in headers else 'BOUNDED_ARCHIVE_WITHOUT_AUTOCONF_EVIDENCE',
      'file':name,'module_bytes':len(data),'module_sha256':hashlib.sha256(data).hexdigest(),'archive':dict(bounds,xz_sha256=hashlib.sha256(archive).hexdigest(),decompressed_tar_bytes=len(raw)),'tar_limits':tar_meta,'selected_headers':headers,'selected_missing':sorted(set(SELECTED_HEADERS)-set(headers)),
      'raw_config_exported':False,'full_header_or_archive_exported':False,'raw_original_dot_config_included_by_source_glob':False,
      'evidence_boundary':'Generated header artifact only. gen_kheaders.sh excludes autoconf.h/compile.h from incremental cache MD5, so stale generated headers remain possible; this is not certification of every stock object compile config. Missing macro is not automatically disabled or unsupported.'}

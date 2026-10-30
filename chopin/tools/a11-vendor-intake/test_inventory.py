"""Metadata-only fake-inode cases; no ext4 dependency, network or device."""
import io
import logging
import stat
import sys
import types
import unittest
from unittest.mock import patch
from vendor_reader import module_directory_inventory, module_manifests
from test_vendor_reader import module_bytes


class Node:
    def __init__(self,name,kind=stat.S_IFREG,size=10,entries=(),data=None):
        self.filename,self.filetype,self.size=name,kind,size
        self.entries,self.data=entries,data
        self.inode=types.SimpleNamespace(i_flags=0)
    def iterdir(self):
        if self.filetype!=stat.S_IFDIR:raise AssertionError("Not a directory")
        yield from self.entries
    def open(self):
        if self.data is None:raise AssertionError("Inventory opened a member file")
        return io.BytesIO(self.data)
    @property
    def link(self):raise AssertionError("Inventory dereferenced a symlink")


class InventoryFixture(unittest.TestCase):
    def directory(self,entries):return Node("modules",stat.S_IFDIR,4096,entries)

    def test_names_size_type_without_member_open_or_recursion(self):
        nodes=[Node("z.ko",size=35),Node("a.ko",stat.S_IFLNK,4),Node("nested",stat.S_IFDIR,4096)]
        snapshots=[]
        result=module_directory_inventory(self.directory(nodes),snapshots.append)
        self.assertTrue(result["complete"])
        self.assertEqual(result["entries"],[{"name":"a.ko","size":4,"type":"symlink"},
            {"name":"nested","size":4096,"type":"directory"},{"name":"z.ko","size":35,"type":"regular"}])
        self.assertEqual(snapshots,[result])
        self.assertFalse(result["member_file_data_read"])

    def test_dot_entries_are_not_paths_to_follow(self):
        result=module_directory_inventory(self.directory([Node(".",stat.S_IFDIR),Node("..",stat.S_IFDIR),Node("met.ko")]))
        self.assertEqual([row["name"]for row in result["entries"]],["met.ko"])

    def test_entry_limit_preserves_partial_metadata_and_rejects(self):
        snapshots=[]
        with self.assertRaisesRegex(ValueError,"limit"):
            module_directory_inventory(self.directory([Node("n"+str(i))for i in range(4097)]),snapshots.append)
        self.assertFalse(snapshots[0]["complete"])
        self.assertEqual(len(snapshots[0]["entries"]),4096)

    def test_invalid_or_duplicate_name_does_not_become_complete(self):
        for second in ("../other","bad\\path.ko","met.ko"):
            snapshots=[]
            with self.assertRaises(ValueError):
                module_directory_inventory(self.directory([Node("met.ko"),Node(second)]),snapshots.append)
            self.assertFalse(snapshots[0]["complete"])
            self.assertEqual(len(snapshots[0]["entries"]),1)

    def test_negative_size_is_not_silently_reported(self):
        snapshots=[]
        with self.assertRaises(ValueError):module_directory_inventory(self.directory([Node("bad.ko",size=-1)]),snapshots.append)
        self.assertFalse(snapshots[0]["complete"])

    def test_reader_warning_is_not_a_complete_inventory(self):
        class WarningDirectory(Node):
            def iterdir(self):
                yield Node("met.ko")
                logging.getLogger("dissect.extfs.extfs").critical("Zero-length directory entry in synthetic fixture")
        snapshots=[]
        with self.assertRaisesRegex(ValueError,"parser warning"):
            module_directory_inventory(WarningDirectory("modules",stat.S_IFDIR,4096),snapshots.append)
        self.assertFalse(snapshots[0]["complete"])
        self.assertEqual(len(snapshots[0]["parser_warnings"]),1)

    def test_fixed_directory_must_be_a_directory_within_old_size_bound(self):
        for node in (Node("modules",stat.S_IFLNK),Node("modules",stat.S_IFDIR,2*1024*1024+1)):
            with self.assertRaises(ValueError):module_directory_inventory(node)

    def test_default_module_path_does_not_inventory_unselected_inodes(self):
        class Unselected:
            filename="unselected.ko"
            @property
            def size(self):raise AssertionError("Default path read an unselected inode's size")
        content=module_bytes()
        met=Node("met.ko",size=len(content),data=content)
        modules=self.directory([Unselected(),met])
        root=Node("/",stat.S_IFDIR,4096,[Node("lib",stat.S_IFDIR,4096,[modules])])
        class ExtFS:
            def __init__(self,partition):
                self.root=root;self.block_size=4096;self.block_count=100
                self.sb=types.SimpleNamespace(s_feature_incompat=0x40,s_state=1)
        fake=types.ModuleType("dissect.extfs.extfs");fake.ExtFS=ExtFS
        with patch.dict(sys.modules,{"dissect":types.ModuleType("dissect"),"dissect.extfs":types.ModuleType("dissect.extfs"),"dissect.extfs.extfs":fake}):
            result,_=module_manifests(types.SimpleNamespace(size=409600),["met.ko"])
        self.assertEqual(result[0]["imports"],{"module_layout":"2d3d4373"})


if __name__=="__main__":unittest.main()

"""Offline parsing and freshness checks. This never launches ADB."""
import copy
import unittest
import uuid
from observe import APP, TARGETS, parse_package_uid, validate_report


class ControllerFixture(unittest.TestCase):
    def setUp(self):
        self.request = str(uuid.uuid4())
        self.uids = {TARGETS[0]: 10002, TARGETS[1]: 10003, APP: 10004}
        queries = []
        for name, which, who in [("self_uid",2,10004),("self_user_zero",2,0),("self_process_zero",0,0),("probe2",2,10002),("probe3",2,10003)]:
            queries.append(dict(name=name, which=which, who=who, direct_arm64_svc=True, raw_return=20,
                raw_errno=0, raw_success_1_to_40=True, raw_out_of_contract=False, interpreted_nice=0,
                libc_syscall_return=20,libc_syscall_errno=0,libc_getpriority_nice=0,libc_getpriority_errno=0,
                sequential_semantics_agree=True))
        self.report = dict(controller_run_id=self.request, run_id=str(uuid.uuid4()), observer_package=APP,
            source_commit="1"*40,native_sha256="2"*64,
            status="observed", root_requested=False, scheduling_writes=False, network_used=False,
            package_manager_verified=True, target_package_uids={key:self.uids[key] for key in TARGETS},
            caller_uid_java=10004, caller_pid_java=1234,
            native=dict(caller_uid_direct=10004, caller_euid_direct=10004, caller_uid_libc=10004,
                caller_pid=1234, caller_context="u:r:untrusted_app_29:s0:c1,c2,c3,c4", ordinary_app_context=True,
                syscall_number=141, queries_are_sequential=True, queries=queries))

    def test_exact_package(self):
        self.assertEqual(parse_package_uid("package:"+TARGETS[0]+" uid:10002\n", TARGETS[0]),10002)

    def test_prefix_package_rejected(self):
        with self.assertRaises(ValueError):parse_package_uid("package:"+TARGETS[0]+"0 uid:10002",TARGETS[0])

    def test_foreign_package_rejected(self):
        with self.assertRaises(ValueError):parse_package_uid("package:other uid:10002","other")

    def test_duplicate_or_missing_package_rejected(self):
        for text in ("",("package:"+TARGETS[0]+" uid:10002\n")*2):
            with self.assertRaises(ValueError):parse_package_uid(text,TARGETS[0])

    def test_valid_report(self):
        self.assertTrue(validate_report(self.report,self.request,self.uids)["self_controls_valid"])

    def test_stale_request(self):
        with self.assertRaises(ValueError):validate_report(self.report,str(uuid.uuid4()),self.uids)

    def test_nonfresh_app_uuid(self):
        self.report["run_id"]=self.request
        with self.assertRaises(ValueError):validate_report(self.report,self.request,self.uids)

    def test_wrong_package_manager_uid(self):
        self.report["target_package_uids"][TARGETS[0]]=10123
        with self.assertRaises(ValueError):validate_report(self.report,self.request,self.uids)

    def test_raw_nice_minus_one_is_success(self):
        item=self.report["native"]["queries"][0]
        item.update(raw_return=21,interpreted_nice=-1,libc_syscall_return=21,libc_getpriority_nice=-1)
        self.assertTrue(validate_report(self.report,self.request,self.uids)["self_controls_valid"])

    def test_raw_zero_is_not_fake_nice_zero(self):
        item=self.report["native"]["queries"][3]
        item.update(raw_return=0,raw_success_1_to_40=False,raw_out_of_contract=True,interpreted_nice=None,sequential_semantics_agree=False)
        self.assertFalse(validate_report(self.report,self.request,self.uids)["raw_contract_valid"])
        item.update(raw_success_1_to_40=True,raw_out_of_contract=False,interpreted_nice=0)
        with self.assertRaises(ValueError):validate_report(self.report,self.request,self.uids)

    def test_esrch_not_inferred_filter_success(self):
        item=self.report["native"]["queries"][3]
        item.update(raw_return=-3,raw_errno=3,raw_success_1_to_40=False,interpreted_nice=None,
                    libc_syscall_return=-1,libc_syscall_errno=3,libc_getpriority_nice=-1,libc_getpriority_errno=3)
        result=validate_report(self.report,self.request,self.uids)
        self.assertTrue(result["raw_contract_valid"])
        self.assertNotIn("filter_passed",result)

    def test_foreign_uid_or_query_rejected(self):
        for changed in (dict(who=12345),dict(which=1),dict(name="foreign")):
            candidate=copy.deepcopy(self.report)
            candidate["native"]["queries"][3].update(changed)
            with self.assertRaises(ValueError):validate_report(candidate,self.request,self.uids)

    def test_root_or_isolated_context_rejected(self):
        for context in ("u:r:ksu:s0","u:r:runas_app:s0:c1,c2","u:r:isolated_app:s0:c1,c2"):
            self.report["native"]["caller_context"]=context
            with self.assertRaises(ValueError):validate_report(self.report,self.request,self.uids)

    def test_java_native_uid_mismatch(self):
        self.report["native"]["caller_uid_direct"]=0
        with self.assertRaises(ValueError):validate_report(self.report,self.request,self.uids)

    def test_wrong_build_identity(self):
        with self.assertRaises(ValueError):validate_report(self.report,self.request,self.uids,
                                                         dict(source_commit="3"*40,native_sha256="2"*64))

    def test_invented_libc_agreement_rejected(self):
        self.report["native"]["queries"][0]["libc_getpriority_nice"]=20
        with self.assertRaises(ValueError):validate_report(self.report,self.request,self.uids)


if __name__ == "__main__":
    unittest.main()

# CI41095 compatibility

The official manager build is 41095 at main96ceb4a4. The pinned, actually boot-tested 4.14 builtin6397fcb5 and paired Arm GNU KPM ABI1 runtime554aa43f are retained. This is a compatibility backport, not a claim that the entire latest builtin or ABI2 runtime was integrated.

The new official userspace tries optional event-aware KPM op8 and falls back to ordinary LOAD on EOPNOTSUPP. The old generic unknown-op branch already returned EOPNOTSUPP. The explicit op8 branch only documents this existing contract; there is no demonstrated old EINVAL regression. The first explanation saying otherwise was wrong and is corrected here.

The actual build changes are the official41095 UAPI declaration and compiled CI/source metadata, plus tests checking no ABI2 operation is sent to the ABI1 backend and ordinary LOAD remains usable. Event-aware loading is not claimed. Actual boot and original-manager regression results must be recorded separately.

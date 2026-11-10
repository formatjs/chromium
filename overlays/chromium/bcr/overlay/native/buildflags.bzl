"""Generated from pinned Linux x86_64 graph; run tools/import_buildflags.py."""

load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":python_action.bzl", "chromium_python_action")

def native_buildflags(name):
    """Declare pinned Chromium buildflag actions.

    Args:
        name: Filegroup collecting generated headers.
    """
    chromium_python_action(
        name = "flags_4a0fe733a7b9f6e6",
        srcs = {"//base/allocator/partition_allocator/src/partition_alloc:write_buildflag_header.py": "base/allocator/partition_allocator/src/partition_alloc/write_buildflag_header.py"},
        script = "base/allocator/partition_allocator/src/partition_alloc/write_buildflag_header.py",
        args = ["--output", "base/allocator/partition_allocator/src/partition_alloc/buildflags.h", "--rulename", "//base/allocator/partition_allocator/src/partition_alloc:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/allocator/partition_allocator/src/partition_alloc/buildflags.h": "gen/base/allocator/partition_allocator/src/partition_alloc/buildflags.h"},
        response_file_contents = ["--flags", "ASSERT_CPP_20=true", "BACKUP_REF_PTR_EXTRA_OOB_CHECKS=true", "BACKUP_REF_PTR_POISON_OOB_PTR=false", "CAN_UNWIND_WITH_FRAME_POINTERS=true", "DCHECKS_ARE_ON=true", "DCHECK_IS_CONFIGURABLE=false", "ENABLE_ALLOCATOR_SHIM_PARTITION_ALLOC_DISPATCH_WITH_ADVANCED_CHECKS_SUPPORT=true", "ENABLE_BACKUP_REF_PTR_FEATURE_FLAG=true", "ENABLE_BACKUP_REF_PTR_INSTANCE_TRACER=false", "ENABLE_BACKUP_REF_PTR_SLOW_CHECKS=false", "ENABLE_BACKUP_REF_PTR_SUPPORT=true", "ENABLE_DANGLING_RAW_PTR_CHECKS=true", "ENABLE_DANGLING_RAW_PTR_FEATURE_FLAG=true", "ENABLE_GWP_ASAN_SUPPORT=true", "ENABLE_PARTITION_LOCK_REENTRANCY_CHECK=false", "ENABLE_PARTITION_LOCK_PRIORITY_INHERITANCE=false", "ENABLE_PKEYS=true", "ENABLE_POINTER_ARITHMETIC_TRAIT_CHECK=true", "ENABLE_POINTER_COMPRESSION=false", "ENABLE_POINTER_SUBTRACTION_CHECK=false", "MOVE_METADATA_OUT_OF_GIGACAGE_FOR_64_BITS_POINTERS=true", "ENABLE_MOVE_METADATA_OUT_OF_GIGACAGE_TRIAL=true", "ENABLE_THREAD_ISOLATION=true", "EXPENSIVE_DCHECKS_ARE_ON=true", "FORCE_DISABLE_BACKUP_REF_PTR_FEATURE=false", "FORCE_ENABLE_RAW_PTR_EXCLUSION=false", "FORWARD_THROUGH_MALLOC=false", "HAS_64_BIT_POINTERS=true", "HAS_MEMORY_TAGGING=false", "IS_ANDROID=false", "IS_CASTOS=false", "IS_CAST_ANDROID=false", "IS_CHROMEOS=false", "IS_DEBUG=false", "IS_HWASAN=false", "RAW_PTR_ZERO_ON_CONSTRUCT=true", "RAW_PTR_ZERO_ON_DESTRUCT=false", "RAW_PTR_ZERO_ON_MOVE=true", "REALLOC_GROWTH_FACTOR_MITIGATION=false", "RECORD_ALLOC_INFO=false", "SHIM_SUPPORTS_SIZED_DEALLOC=false", "SMALLER_PARTITION_COOKIE=false", "STACK_SCAN_SUPPORTED=true", "USE_ALLOCATOR_SHIM=true", "USE_ASAN_BACKUP_REF_PTR=false", "USE_FULL_MTE=false", "USE_LARGE_EMPTY_SLOT_SPAN_RING=true", "USE_PARTITION_ALLOC=true", "USE_PARTITION_ALLOC_AS_MALLOC=true", "USE_PARTITION_COOKIE=true", "USE_RAW_PTR_ASAN_UNOWNED_IMPL=false", "USE_RAW_PTR_BACKUP_REF_IMPL=true", "USE_RAW_PTR_HOOKABLE_IMPL=false"],
    )
    chromium_python_action(
        name = "flags_6a6faeb3837876da",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/allocator/buildflags.h", "--rulename", "//base/allocator:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/allocator/buildflags.h": "gen/base/allocator/buildflags.h"},
        response_file_contents = ["--flags", "USE_PARTITION_ALLOC_AS_GWP_ASAN_STORE=true"],
    )
    chromium_python_action(
        name = "flags_4adb3f90976138a7",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/android/library_loader/anchor_functions_buildflags.h", "--rulename", "//base:anchor_functions_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/android/library_loader/anchor_functions_buildflags.h": "gen/base/android/library_loader/anchor_functions_buildflags.h"},
        response_file_contents = ["--flags", "USE_LLD=true", "SUPPORTS_CODE_ORDERING=false"],
    )
    chromium_python_action(
        name = "flags_8e0709a9e3a1309d",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/cfi_buildflags.h", "--rulename", "//base:cfi_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/cfi_buildflags.h": "gen/base/cfi_buildflags.h"},
        response_file_contents = ["--flags", "CFI_CAST_CHECK=false", "CFI_DIAG=false", "CFI_ICALL_CHECK=false", "CFI_ENFORCEMENT_TRAP=false", "CFI_ENFORCEMENT_DIAGNOSTIC=false"],
    )
    chromium_python_action(
        name = "flags_81151354f19f1afa",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/clang_profiling_buildflags.h", "--rulename", "//base:clang_profiling_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/clang_profiling_buildflags.h": "gen/base/clang_profiling_buildflags.h"},
        response_file_contents = ["--flags", "CLANG_PROFILING=false", "CLANG_PROFILING_INSIDE_SANDBOX=false", "USE_CLANG_COVERAGE=false"],
    )
    chromium_python_action(
        name = "flags_c0d8c63cf51403c4",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/debug/debugging_buildflags.h", "--rulename", "//base:debugging_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/debug/debugging_buildflags.h": "gen/base/debug/debugging_buildflags.h"},
        response_file_contents = ["--flags", "DCHECK_IS_CONFIGURABLE=false", "ENABLE_PROFILING=false", "CAN_UNWIND_WITH_FRAME_POINTERS=true", "UNSAFE_DEVELOPER_BUILD=true", "CAN_UNWIND_WITH_CFI_TABLE=false", "EXCLUDE_UNWIND_TABLES=false", "ENABLE_GDBINIT_WARNING=false", "ENABLE_LLDBINIT_WARNING=false", "EXPENSIVE_DCHECKS_ARE_ON=true", "ENABLE_STACK_TRACE_LINE_NUMBERS=false", "ENABLE_COMMANDLINE_SEQUENCE_CHECKS=true", "ENABLE_ALLOCATION_STACK_TRACE_RECORDER=false", "ENABLE_ALLOCATION_TRACE_RECORDER_FULL_REPORTING=false", "PRINT_UNSYMBOLIZED_STACK_TRACES=false"],
    )
    cc_library(
        name = "debugging_buildflags",
        hdrs = [":flags_c0d8c63cf51403c4"],
        includes = ["gen"],
        deps = ["//build:buildflag"],
    )
    chromium_python_action(
        name = "flags_3f21f430a9782828",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/feature_list_buildflags.h", "--rulename", "//base:feature_list_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/feature_list_buildflags.h": "gen/base/feature_list_buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_BANNED_BASE_FEATURE_PREFIX=false"],
    )
    chromium_python_action(
        name = "flags_1253acc8a725ddc4",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/fuzzing_buildflags.h", "--rulename", "//base:fuzzing_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/fuzzing_buildflags.h": "gen/base/fuzzing_buildflags.h"},
        response_file_contents = ["--flags", "USE_FUZZING_ENGINE=false"],
    )
    chromium_python_action(
        name = "flags_58a0769af7adeddc",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/i18n/transliterator_buildflags.h", "--rulename", "//base:i18n_transliterator", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/i18n/transliterator_buildflags.h": "gen/base/i18n/transliterator_buildflags.h"},
        response_file_contents = ["--flags", "BUILD_RUST_TRANSLIT=false"],
    )
    chromium_python_action(
        name = "flags_4108a3a8378cd80c",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/message_loop/ios_cronet_buildflags.h", "--rulename", "//base:ios_cronet_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/message_loop/ios_cronet_buildflags.h": "gen/base/message_loop/ios_cronet_buildflags.h"},
        response_file_contents = ["--flags", "CRONET_BUILD=false"],
    )
    chromium_python_action(
        name = "flags_9f913a7112e3928c",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/android/orderfile/orderfile_buildflags.h", "--rulename", "//base:orderfile_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/android/orderfile/orderfile_buildflags.h": "gen/base/android/orderfile/orderfile_buildflags.h"},
        response_file_contents = ["--flags", "DEVTOOLS_INSTRUMENTATION_DUMPING=false", "ORDERFILE_INSTRUMENTATION=false"],
    )
    chromium_python_action(
        name = "flags_5b72dc0e3098f3e6",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/power_monitor/power_monitor_buildflags.h", "--rulename", "//base:power_monitor_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/power_monitor/power_monitor_buildflags.h": "gen/base/power_monitor/power_monitor_buildflags.h"},
        response_file_contents = ["--flags", "HAS_BATTERY_LEVEL_PROVIDER_IMPL=false"],
    )
    chromium_python_action(
        name = "flags_368b50dddafa53d9",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/profiler/profiler_buildflags.h", "--rulename", "//base:profiler_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/profiler/profiler_buildflags.h": "gen/base/profiler/profiler_buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_ARM_CFI_TABLE=false", "IOS_STACK_PROFILER_ENABLED=true"],
    )
    chromium_python_action(
        name = "flags_43e5bf28b09ed7e9",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/memory/protected_memory_buildflags.h", "--rulename", "//base:protected_memory_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/memory/protected_memory_buildflags.h": "gen/base/memory/protected_memory_buildflags.h"},
        response_file_contents = ["--flags", "PROTECTED_MEMORY_ENABLED=true"],
    )
    chromium_python_action(
        name = "flags_89020abe85087279",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/sanitizer_buildflags.h", "--rulename", "//base:sanitizer_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/sanitizer_buildflags.h": "gen/base/sanitizer_buildflags.h"},
        response_file_contents = ["--flags", "IS_HWASAN=false", "IS_UBSAN=false", "IS_UBSAN_SECURITY=false", "USING_SANITIZER=false"],
    )
    chromium_python_action(
        name = "flags_79eda2c62c056f4e",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/synchronization/synchronization_buildflags.h", "--rulename", "//base:synchronization_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/synchronization/synchronization_buildflags.h": "gen/base/synchronization/synchronization_buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_MUTEX_PRIORITY_INHERITANCE=false"],
    )
    chromium_python_action(
        name = "flags_e0c2bfdeb42485bf",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "base/tracing_buildflags.h", "--rulename", "//base:tracing_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/base/tracing_buildflags.h": "gen/base/tracing_buildflags.h"},
        response_file_contents = ["--flags", "USE_PERFETTO_TRACE_PROCESSOR=true", "OPTIONAL_TRACE_EVENTS_ENABLED=true"],
    )
    chromium_python_action(
        name = "flags_3c33d3e57bf90d92",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "build/config/chromebox_for_meetings/buildflags.h", "--rulename", "//build/config/chromebox_for_meetings:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/build/config/chromebox_for_meetings/buildflags.h": "gen/build/config/chromebox_for_meetings/buildflags.h"},
        response_file_contents = ["--flags", "PLATFORM_CFM=false"],
    )
    chromium_python_action(
        name = "flags_c62c00b03a3133ce",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "build/config/compiler/compiler_buildflags.h", "--rulename", "//build/config/compiler:compiler_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/build/config/compiler/compiler_buildflags.h": "gen/build/config/compiler/compiler_buildflags.h"},
        response_file_contents = ["--flags", "CLANG_PGO_PROFILING=false", "CLANG_PGO_OPTIMIZED=false", "HAS_SYMBOLS=false"],
    )
    chromium_python_action(
        name = "flags_7f150688c68d3bd4",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "build/config/linux/dbus/buildflags.h", "--rulename", "//build/config/linux/dbus:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/build/config/linux/dbus/buildflags.h": "gen/build/config/linux/dbus/buildflags.h"},
        response_file_contents = ["--flags", "USE_DBUS=true"],
    )
    chromium_python_action(
        name = "flags_0640069825305db6",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "build/rust/allocator/buildflags.h", "--rulename", "//build/rust/allocator:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/build/rust/allocator/buildflags.h": "gen/build/rust/allocator/buildflags.h"},
        response_file_contents = ["--flags", "RUST_ALLOCATOR_USES_PARTITION_ALLOC=true", "RUST_ALLOCATOR_USES_ALIGNED_MALLOC=false"],
    )
    chromium_python_action(
        name = "flags_eb3aab2d26244c93",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "build/android_buildflags.h", "--rulename", "//build:android_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/build/android_buildflags.h": "gen/build/android_buildflags.h"},
        response_file_contents = ["--flags", "IS_DESKTOP_ANDROID=false"],
    )
    chromium_python_action(
        name = "flags_254bdcedfad33bc7",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "build/blink_buildflags.h", "--rulename", "//build:blink_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/build/blink_buildflags.h": "gen/build/blink_buildflags.h"},
        response_file_contents = ["--flags", "USE_BLINK=true"],
    )
    chromium_python_action(
        name = "flags_ec1c86a4ff0e22de",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "build/branding_buildflags.h", "--rulename", "//build:branding_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/build/branding_buildflags.h": "gen/build/branding_buildflags.h"},
        response_file_contents = ["--flags", "CHROMIUM_BRANDING=true", "GOOGLE_CHROME_BRANDING=false", "CHROME_FOR_TESTING=false", "GOOGLE_CHROME_FOR_TESTING_BRANDING=false", "ENABLE_BUILTIN_SEARCH_PROVIDER_ASSETS=false"],
    )
    chromium_python_action(
        name = "flags_5ac8dcfcbd0949e3",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "build/chromecast_buildflags.h", "--rulename", "//build:chromecast_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/build/chromecast_buildflags.h": "gen/build/chromecast_buildflags.h"},
        response_file_contents = ["--flags", "IS_CASTOS=false", "IS_CAST_ANDROID=false", "ENABLE_CAST_RECEIVER=false"],
    )
    chromium_python_action(
        name = "flags_700c9f3ea0d9460e",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "build/chromeos_buildflags.h", "--rulename", "//build:chromeos_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/build/chromeos_buildflags.h": "gen/build/chromeos_buildflags.h"},
        response_file_contents = ["--flags", "IS_CHROMEOS_DEVICE=false", "IS_CHROMEOS_ASH=false", "IS_CHROMEOS_WITH_HW_DETAILS=false", "IS_REVEN=false"],
    )
    chromium_python_action(
        name = "flags_e47bada76fbc9ee6",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "build/ios_buildflags.h", "--rulename", "//build:ios_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/build/ios_buildflags.h": "gen/build/ios_buildflags.h"},
        response_file_contents = ["--flags", "IS_IOS_APP_EXTENSION=false"],
    )
    chromium_python_action(
        name = "flags_87f66ff3811569ec",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "build/robolectric_buildflags.h", "--rulename", "//build:robolectric_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/build/robolectric_buildflags.h": "gen/build/robolectric_buildflags.h"},
        response_file_contents = ["--flags", "IS_ROBOLECTRIC=false"],
    )
    chromium_python_action(
        name = "flags_971c9346a9306ed5",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "chrome/browser/page_info/page_info_buildflags.h", "--rulename", "//chrome/browser/page_info:page_info_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/chrome/browser/page_info/page_info_buildflags.h": "gen/chrome/browser/page_info/page_info_buildflags.h"},
        response_file_contents = ["--flags", "PAGE_INFO_USE_INTERNAL_ANDROID_RESOURCES=false"],
    )
    chromium_python_action(
        name = "flags_e86b94280348bf30",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "chrome/browser/sharing/buildflags.h", "--rulename", "//chrome/browser/sharing:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/chrome/browser/sharing/buildflags.h": "gen/chrome/browser/sharing/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_DISCOVERY=false"],
    )
    chromium_python_action(
        name = "flags_10991f8e7c2e395e",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "chrome/browser/buildflags.h", "--rulename", "//chrome/browser:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/chrome/browser/buildflags.h": "gen/chrome/browser/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_UPDATER=false", "ENABLE_UPDATE_NOTIFICATIONS=false", "USE_MINIKIN_HYPHENATION=true", "USE_THIN_LTO=false", "ENABLE_PROCESS_SINGLETON=true"],
    )
    chromium_python_action(
        name = "flags_c5256b5b57a57dfd",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "chrome/common/printing/printing_buildflags.h", "--rulename", "//chrome/common/printing:printing_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/chrome/common/printing/printing_buildflags.h": "gen/chrome/common/printing/printing_buildflags.h"},
        response_file_contents = ["--flags", "PRINT_MEDIA_L10N_ENABLED=false"],
    )
    chromium_python_action(
        name = "flags_e375ca1c2f3a5cc4",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "chrome/common/request_header_integrity/buildflags.h", "--rulename", "//chrome/common/request_header_integrity:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/chrome/common/request_header_integrity/buildflags.h": "gen/chrome/common/request_header_integrity/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_REQUEST_HEADER_INTEGRITY=false"],
    )
    chromium_python_action(
        name = "flags_0df2092a616eaabc",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "chrome/common/buildflags.h", "--rulename", "//chrome/common:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/chrome/common/buildflags.h": "gen/chrome/common/buildflags.h"},
        response_file_contents = ["--flags", "CHROME_ENABLE_LOGGING_BY_DEFAULT=false", "CHROME_ROOT_STORE_CERT_MANAGEMENT_UI=true", "ENABLE_ANDROID_SITE_ISOLATION=false", "ENABLE_BACKGROUND_MODE=true", "ENABLE_BACKGROUND_CONTENTS=true", "ENABLE_CHROME_NOTIFICATIONS=true", "ENABLE_DOWNGRADE_PROCESSING=true", "ENABLE_GLIC=true", "ENABLE_HANGOUT_SERVICES_EXTENSION=false", "ENABLE_PDF_SAVE_TO_DRIVE=true", "ENABLE_SERVICE_DISCOVERY=true", "ENABLE_SESSION_SERVICE=true", "ENABLE_WEBUI_CERTIFICATE_VIEWER=true", "ENABLE_WEBUI_TAB_STRIP=true", "OPTIMIZE_WEBUI=true"],
    )
    chromium_python_action(
        name = "flags_aa7f27e14766b296",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "chrome/install_static/buildflags.h", "--rulename", "//chrome/install_static:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/chrome/install_static/buildflags.h": "gen/chrome/install_static/buildflags.h"},
        response_file_contents = ["--flags", "USE_GOOGLE_UPDATE_INTEGRATION=false"],
    )
    chromium_python_action(
        name = "flags_bcb592b9958432a8",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "chrome/services/file_util/buildflags.h", "--rulename", "//chrome/services/file_util:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/chrome/services/file_util/buildflags.h": "gen/chrome/services/file_util/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_EXTRACTORS=true"],
    )
    chromium_python_action(
        name = "flags_9e9bee6c8484bb92",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "chrome/services/speech/buildflags/buildflags.h", "--rulename", "//chrome/services/speech/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/chrome/services/speech/buildflags/buildflags.h": "gen/chrome/services/speech/buildflags/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_SPEECH_SERVICE=true", "ENABLE_BROWSER_SPEECH_SERVICE=true", "ENABLE_SERVER_BASED_RECOGNITION_RECOGNIZER=false"],
    )
    chromium_python_action(
        name = "flags_520d9f2f121ab24e",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/autofill/core/browser/form_parsing/buildflags.h", "--rulename", "//components/autofill/core/browser:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/autofill/core/browser/form_parsing/buildflags.h": "gen/components/autofill/core/browser/form_parsing/buildflags.h"},
        response_file_contents = ["--flags", "USE_INTERNAL_AUTOFILL_PATTERNS=false"],
    )
    chromium_python_action(
        name = "flags_a3fb1f6d19e9eaa9",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/captive_portal/core/buildflags.h", "--rulename", "//components/captive_portal/core:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/captive_portal/core/buildflags.h": "gen/components/captive_portal/core/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_CAPTIVE_PORTAL_DETECTION=true"],
    )
    chromium_python_action(
        name = "flags_763ee8bf6dcdbbbc",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/cdm/common/buildflags.h", "--rulename", "//components/cdm/common:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/cdm/common/buildflags.h": "gen/components/cdm/common/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_PLAYREADY=false"],
    )
    chromium_python_action(
        name = "flags_a141a308871c7aea",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/compose/buildflags.h", "--rulename", "//components/compose:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/compose/buildflags.h": "gen/components/compose/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_COMPOSE=true"],
    )
    chromium_python_action(
        name = "flags_bac1f758d1314d23",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/contextual_search/buildflags.h", "--rulename", "//components/contextual_search:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/contextual_search/buildflags.h": "gen/components/contextual_search/buildflags.h"},
        response_file_contents = ["--flags", "BUILD_CONTEXTUAL_SEARCH=false"],
    )
    chromium_python_action(
        name = "flags_b0769cef119d5457",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/crash/core/common/crash_buildflags.h", "--rulename", "//components/crash/core/common:crash_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/crash/core/common/crash_buildflags.h": "gen/components/crash/core/common/crash_buildflags.h"},
        response_file_contents = ["--flags", "USE_CRASHPAD_ANNOTATION=true", "USE_CRASH_KEY_STUBS=false"],
    )
    chromium_python_action(
        name = "flags_8bc78244895640c4",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/enterprise/buildflags/buildflags.h", "--rulename", "//components/enterprise/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/enterprise/buildflags/buildflags.h": "gen/components/enterprise/buildflags/buildflags.h"},
        response_file_contents = ["--flags", "ENTERPRISE_CLOUD_CONTENT_ANALYSIS=true", "ENTERPRISE_LOCAL_CONTENT_ANALYSIS=true", "ENTERPRISE_CONTENT_ANALYSIS=true", "ENTERPRISE_DATA_CONTROLS=true", "ENTERPRISE_CLIENT_CERTIFICATES=true", "ENTERPRISE_WATERMARK=true", "ENTERPRISE_SCREENSHOT_PROTECTION=false", "ENTERPRISE_TELOMERE_REPORTING=true"],
    )
    chromium_python_action(
        name = "flags_ad763c8c1d0947e2",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/gcm_driver/gcm_buildflags.h", "--rulename", "//components/gcm_driver:gcm_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/gcm_driver/gcm_buildflags.h": "gen/components/gcm_driver/gcm_buildflags.h"},
        response_file_contents = ["--flags", "USE_GCM_FROM_PLATFORM=false"],
    )
    chromium_python_action(
        name = "flags_c07dc84e5218ae8e",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/guest_view/buildflags/buildflags.h", "--rulename", "//components/guest_view/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/guest_view/buildflags/buildflags.h": "gen/components/guest_view/buildflags/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_GUEST_VIEW=true"],
    )
    chromium_python_action(
        name = "flags_ada7700a133b8fa9",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/gwp_asan/buildflags/buildflags.h", "--rulename", "//components/gwp_asan/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/gwp_asan/buildflags/buildflags.h": "gen/components/gwp_asan/buildflags/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_GWP_ASAN_MALLOC=true", "ENABLE_GWP_ASAN_PARTITIONALLOC=true", "ENABLE_GWP_ASAN=true"],
    )
    chromium_python_action(
        name = "flags_4e963e221e3430c1",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/keyed_service/core/features_buildflags.h", "--rulename", "//components/keyed_service/core:features", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/keyed_service/core/features_buildflags.h": "gen/components/keyed_service/core/features_buildflags.h"},
        response_file_contents = ["--flags", "KEYED_SERVICE_HAS_TIGHT_REGISTRATION=false", "KEYED_SERVICE_HAS_TIGHT_INITIALIZATION=false", "KEYED_SERVICE_HAS_DEPRECATED_ASSOCIATE_API=true"],
    )
    chromium_python_action(
        name = "flags_6340ff1be00afd64",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/lens/buildflags.h", "--rulename", "//components/lens:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/lens/buildflags.h": "gen/components/lens/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_LENS_DESKTOP=true", "ENABLE_LENS_DESKTOP_GOOGLE_BRANDED_FEATURES=false"],
    )
    chromium_python_action(
        name = "flags_ab6a1e461cb0bca6",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/metrics/structured/buildflags/buildflags.h", "--rulename", "//components/metrics/structured/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/metrics/structured/buildflags/buildflags.h": "gen/components/metrics/structured/buildflags/buildflags.h"},
        response_file_contents = ["--flags", "STRUCTURED_METRICS_ENABLED=true", "STRUCTURED_METRICS_DEBUG_ENABLED=true"],
    )
    chromium_python_action(
        name = "flags_9fa1d269dba1a63c",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/offline_pages/buildflags/buildflags.h", "--rulename", "//components/offline_pages/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/offline_pages/buildflags/buildflags.h": "gen/components/offline_pages/buildflags/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_OFFLINE_PAGES=false", "ENABLE_OFFLINE_PAGES_HARNESS=false"],
    )
    chromium_python_action(
        name = "flags_52458918bcf86ad2",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/omnibox/browser/buildflags.h", "--rulename", "//components/omnibox/browser:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/omnibox/browser/buildflags.h": "gen/components/omnibox/browser/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_VR=true"],
    )
    chromium_python_action(
        name = "flags_ffd81efe95053b99",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/optimization_guide/machine_learning_tflite_buildflags.h", "--rulename", "//components/optimization_guide:machine_learning_tflite_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/optimization_guide/machine_learning_tflite_buildflags.h": "gen/components/optimization_guide/machine_learning_tflite_buildflags.h"},
        response_file_contents = ["--flags", "BUILD_WITH_MEDIAPIPE_LIB=false", "BUILD_WITH_TFLITE_LIB=true"],
    )
    chromium_python_action(
        name = "flags_589c48104ee99bd4",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/optimization_guide/optimization_guide_buildflags.h", "--rulename", "//components/optimization_guide:optimization_guide_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/optimization_guide/optimization_guide_buildflags.h": "gen/components/optimization_guide/optimization_guide_buildflags.h"},
        response_file_contents = ["--flags", "BUILD_WITH_INTERNAL_OPTIMIZATION_GUIDE=false", "BUILD_WITH_MODEL_EXECUTION=true"],
    )
    chromium_python_action(
        name = "flags_5b0ce081be7bc4cd",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/paint_preview/buildflags/buildflags.h", "--rulename", "//components/paint_preview/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/paint_preview/buildflags/buildflags.h": "gen/components/paint_preview/buildflags/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_PAINT_PREVIEW=true"],
    )
    chromium_python_action(
        name = "flags_deb476db6783e7d9",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/password_manager/core/browser/password_manager_buildflags.h", "--rulename", "//components/password_manager/core/browser:password_manager_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/password_manager/core/browser/password_manager_buildflags.h": "gen/components/password_manager/core/browser/password_manager_buildflags.h"},
        response_file_contents = ["--flags", "PASSWORD_MANAGER_USE_INTERNAL_ANDROID_RESOURCES=false"],
    )
    chromium_python_action(
        name = "flags_2217c92c8e677750",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/safe_browsing/buildflags.h", "--rulename", "//components/safe_browsing:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/safe_browsing/buildflags.h": "gen/components/safe_browsing/buildflags.h"},
        response_file_contents = ["--flags", "FULL_SAFE_BROWSING=true", "SAFE_BROWSING_AVAILABLE=true", "SAFE_BROWSING_DB_LOCAL=true", "SAFE_BROWSING_DB_REMOTE=false", "SAFE_BROWSING_DOWNLOAD_PROTECTION=true"],
    )
    chromium_python_action(
        name = "flags_ef4b17a8f582ebc0",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/search_engines/search_engine_choice/buildflags.h", "--rulename", "//components/search_engines/search_engine_choice:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/search_engines/search_engine_choice/buildflags.h": "gen/components/search_engines/search_engine_choice/buildflags.h"},
        response_file_contents = ["--flags", "CHOICE_SCREEN_IN_CHROME=true"],
    )
    chromium_python_action(
        name = "flags_aac6e5cb03eaf0be",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/services/on_device_translation/buildflags/buildflags.h", "--rulename", "//components/services/on_device_translation/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/services/on_device_translation/buildflags/buildflags.h": "gen/components/services/on_device_translation/buildflags/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_ON_DEVICE_TRANSLATION=true"],
    )
    chromium_python_action(
        name = "flags_5163c7d9ce554144",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/sharing_message/buildflags.h", "--rulename", "//components/sharing_message:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/sharing_message/buildflags.h": "gen/components/sharing_message/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_DISCOVERY=false", "ENABLE_CLICK_TO_CALL=true"],
    )
    chromium_python_action(
        name = "flags_1e61c92b9e74f26b",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/signin/public/base/signin_buildflags.h", "--rulename", "//components/signin/public/base:signin_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/signin/public/base/signin_buildflags.h": "gen/components/signin/public/base/signin_buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_DICE_SUPPORT=true", "ENABLE_MIRROR=false", "ENABLE_BOUND_SESSION_CREDENTIALS=true"],
    )
    chromium_python_action(
        name = "flags_4160b12b45f69f4c",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/soda/buildflags.h", "--rulename", "//components/soda:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/soda/buildflags.h": "gen/components/soda/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_SODA_INTEGRATION_TESTS=false"],
    )
    chromium_python_action(
        name = "flags_8828c4cef7335afa",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/spellcheck/spellcheck_buildflags.h", "--rulename", "//components/spellcheck:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/spellcheck/spellcheck_buildflags.h": "gen/components/spellcheck/spellcheck_buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_SPELLCHECK=true", "USE_BROWSER_SPELLCHECKER=false", "USE_RENDERER_SPELLCHECKER=true", "ENABLE_SPELLING_SERVICE=true", "HAS_SPELLCHECK_PANEL=false"],
    )
    chromium_python_action(
        name = "flags_b58bf161c4020769",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/supervised_user/core/common/buildflags.h", "--rulename", "//components/supervised_user/core/common:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/supervised_user/core/common/buildflags.h": "gen/components/supervised_user/core/common/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_SUPERVISED_USERS=true"],
    )
    chromium_python_action(
        name = "flags_f3da8a2600443da2",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/system_media_controls/linux/buildflags/buildflags.h", "--rulename", "//components/system_media_controls/linux/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/system_media_controls/linux/buildflags/buildflags.h": "gen/components/system_media_controls/linux/buildflags/buildflags.h"},
        response_file_contents = ["--flags", "USE_MPRIS=true"],
    )
    chromium_python_action(
        name = "flags_8f4b7865250bd883",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/variations/service/buildflags.h", "--rulename", "//components/variations/service:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/variations/service/buildflags.h": "gen/components/variations/service/buildflags.h"},
        response_file_contents = ["--flags", "FIELDTRIAL_TESTING_ENABLED=true"],
    )
    chromium_python_action(
        name = "flags_b1d6f652768b5fb7",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/variations/buildflags.h", "--rulename", "//components/variations:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/variations/buildflags.h": "gen/components/variations/buildflags.h"},
        response_file_contents = ["--flags", "LARGE_VARIATION_KEY_SIZE=false"],
    )
    chromium_python_action(
        name = "flags_57ce1ae95c9f7f03",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/viz/common/buildflags.h", "--rulename", "//components/viz/common:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/viz/common/buildflags.h": "gen/components/viz/common/buildflags.h"},
        response_file_contents = ["--flags", "USE_VIZ_DEBUGGER=true", "ENABLE_CAST_OVERLAY_STRATEGY=false", "ALWAYS_ENABLE_BLENDING_FOR_PRIMARY=false"],
    )
    chromium_python_action(
        name = "flags_3af9e0dfaf81948c",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "components/zucchini/buildflags.h", "--rulename", "//components/zucchini:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/components/zucchini/buildflags.h": "gen/components/zucchini/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_DEX=true", "ENABLE_ELF=true", "ENABLE_WIN=true", "ENABLE_ZTF=true"],
    )
    chromium_python_action(
        name = "flags_d00145fd5e430d8d",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "content/common/buildflags.h", "--rulename", "//content/common:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/content/common/buildflags.h": "gen/content/common/buildflags.h"},
        response_file_contents = ["--flags", "USE_EXTERNAL_POPUP_MENU=false", "ALLOW_CRITICAL_MEMORY_PRESSURE_HANDLING_IN_FOREGROUND=false", "MBI_MODE_PER_RENDER_PROCESS_HOST=false", "MBI_MODE_PER_SITE_INSTANCE=false", "CONTENT_ENABLE_LEGACY_IPC=0"],
    )
    chromium_python_action(
        name = "flags_037f56cbccbc4d50",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "content/public/common/zygote/zygote_buildflags.h", "--rulename", "//content/public/common/zygote:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/content/public/common/zygote/zygote_buildflags.h": "gen/content/public/common/zygote/zygote_buildflags.h"},
        response_file_contents = ["--flags", "USE_ZYGOTE=true"],
    )
    chromium_python_action(
        name = "flags_37cc4cd31fda8bb3",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "content/public/common/buildflags.h", "--rulename", "//content/public/common:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/content/public/common/buildflags.h": "gen/content/public/common/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_DEVTOOLS_FRONTEND=true", "ENABLE_PLUGINS=true", "ENABLE_SCREEN_CAPTURE=true", "LOAD_WEBUI_FROM_DISK=false"],
    )
    chromium_python_action(
        name = "flags_427bd7b2efd21661",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "crypto/crypto_buildflags.h", "--rulename", "//crypto:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/crypto/crypto_buildflags.h": "gen/crypto/crypto_buildflags.h"},
        response_file_contents = ["--flags", "USE_NSS_CERTS=true"],
    )
    chromium_python_action(
        name = "flags_1519a75c7d61d445",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "device/vr/buildflags/buildflags.h", "--rulename", "//device/vr/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/device/vr/buildflags/buildflags.h": "gen/device/vr/buildflags/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_ARCORE=false", "ENABLE_VR=true", "ENABLE_OPENXR=false", "ENABLE_CARDBOARD=false"],
    )
    chromium_python_action(
        name = "flags_d9c9e95aefb43522",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "extensions/buildflags/buildflags.h", "--rulename", "//extensions/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/extensions/buildflags/buildflags.h": "gen/extensions/buildflags/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_EXTENSIONS=true", "ENABLE_DESKTOP_ANDROID_EXTENSIONS=false", "ENABLE_EXTENSIONS_CORE=true", "ENABLE_PLATFORM_APPS=true"],
    )
    chromium_python_action(
        name = "flags_5939b67cd19c3e20",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "google_apis/buildflags.h", "--rulename", "//google_apis:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/google_apis/buildflags.h": "gen/google_apis/buildflags.h"},
        response_file_contents = ["--flags", "SUPPORT_EXTERNAL_GOOGLE_API_KEY=false"],
    )
    chromium_python_action(
        name = "flags_68d58eb2ae10d315",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "gpu/vulkan/buildflags.h", "--rulename", "//gpu/vulkan:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/gpu/vulkan/buildflags.h": "gen/gpu/vulkan/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_VULKAN=true"],
    )
    chromium_python_action(
        name = "flags_6157a8233d1bc7b8",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "media/gpu/buildflags.h", "--rulename", "//media/gpu:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/media/gpu/buildflags.h": "gen/media/gpu/buildflags.h"},
        response_file_contents = ["--flags", "USE_AV1_HW_DECODER=true", "USE_VAAPI=true", "USE_VAAPI_IMAGE_CODECS=false", "USE_V4L2_CODEC=false", "USE_LIBV4L2=false", "USE_LINUX_VIDEO_ACCELERATION=true"],
    )
    chromium_python_action(
        name = "flags_5fcdf86d6913d966",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "media/mojo/buildflags.h", "--rulename", "//media/mojo:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/media/mojo/buildflags.h": "gen/media/mojo/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_CAST_RENDERER=false", "ENABLE_MOJO_RENDERER=false", "ENABLE_MOJO_CDM=true", "ENABLE_MOJO_AUDIO_DECODER=false", "ENABLE_MOJO_AUDIO_ENCODER=false", "ENABLE_MOJO_VIDEO_DECODER=true", "ENABLE_MOJO_MEDIA_IN_BROWSER_PROCESS=false", "ENABLE_MOJO_MEDIA_IN_GPU_PROCESS=true"],
    )
    chromium_python_action(
        name = "flags_b46d8228bf7002c1",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "media/media_buildflags.h", "--rulename", "//media:media_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/media/media_buildflags.h": "gen/media/media_buildflags.h"},
        response_file_contents = ["--flags", "ALLOW_OOP_VIDEO_DECODER=true", "ALLOW_HOSTING_OOP_VIDEO_DECODER=true", "ALTERNATE_CDM_STORAGE_ID_KEY=\"\"", "CHROME_WIDE_ECHO_CANCELLATION=true", "SYSTEM_LOOPBACK_AS_AEC_REFERENCE=false", "ENABLE_PLATFORM_AC3_EAC3_AUDIO=false", "ENABLE_PLATFORM_AC4_AUDIO=false", "ENABLE_CAST_AUDIO_RENDERER=false", "ENABLE_DAV1D_DECODER=true", "ENABLE_AV1_DECODER=true", "ENABLE_PLATFORM_DOLBY_VISION=false", "ENABLE_PLATFORM_ENCRYPTED_DOLBY_VISION=false", "ENABLE_FFMPEG=true", "ENABLE_FFMPEG_VIDEO_DECODERS=true", "ENABLE_PLATFORM_HEVC=false", "ENABLE_HEVC_PARSER_AND_HW_DECODER=false", "ENABLE_PLATFORM_VVC=false", "ENABLE_HLS_DEMUXER=false", "ENABLE_LIBAOM=true", "ENABLE_LIBRARY_CDMS=true", "ENABLE_LIBVPX=true", "ENABLE_LOGGING_OVERRIDE=false", "ENABLE_MEDIA_DRM_STORAGE=false", "ENABLE_MEDIA_REMOTING=true", "ENABLE_MEDIA_REMOTING_RPC=true", "ENABLE_OPENH264=false", "ENABLE_PASSTHROUGH_AUDIO_CODECS=false", "ENABLE_PLATFORM_DTS_AUDIO=false", "ENABLE_PLATFORM_IAMF_AUDIO=false", "ENABLE_PLATFORM_MPEG_H_AUDIO=false", "ENABLE_MSE_MPEG2TS_STREAM_PARSER=false", "ENABLE_SYMPHONIA=true", "PLATFORM_HAS_OPTIONAL_HEVC_DECODE_SUPPORT=false", "PLATFORM_HAS_OPTIONAL_HEVC_ENCODE_SUPPORT=false", "USE_ARC_PROTECTED_MEDIA=false", "USE_CHROMEOS_PROTECTED_AV1=false", "USE_CHROMEOS_PROTECTED_MEDIA=false", "USE_CRAS=false", "USE_PROPRIETARY_CODECS=false", "ENABLE_GPU_CHANNEL_MEDIA_CAPTURE=true", "USE_OPENSLES=true", "USE_LINUX_VIDEO_ACCELERATION=true", "CDM_PLATFORM_SPECIFIC_PATH=\"_platform_specific/linux_x64\"", "ENABLE_CDM_HOST_VERIFICATION=false", "ENABLE_CDM_STORAGE_ID=false"],
    )
    chromium_python_action(
        name = "flags_fc79f1e1e84eb816",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "mojo/public/cpp/bindings/mojo_buildflags.h", "--rulename", "//mojo/public/cpp/bindings:mojo_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/mojo/public/cpp/bindings/mojo_buildflags.h": "gen/mojo/public/cpp/bindings/mojo_buildflags.h"},
        response_file_contents = ["--flags", "MOJO_TRACE_ENABLED=false", "MOJO_RANDOM_DELAYS_ENABLED=false"],
    )
    chromium_python_action(
        name = "flags_9555339617b91e30",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "mojo/buildflags.h", "--rulename", "//mojo:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/mojo/buildflags.h": "gen/mojo/buildflags.h"},
        response_file_contents = ["--flags", "MOJO_USE_APPLE_CHANNEL=false", "MOJO_SUPPORT_LEGACY_CORE=false"],
    )
    chromium_python_action(
        name = "flags_91600bf120c1ff21",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "net/net_buildflags.h", "--rulename", "//net:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/net/net_buildflags.h": "gen/net/net_buildflags.h"},
        response_file_contents = ["--flags", "POSIX_BYPASS_MMAP=false", "DISABLE_FILE_SUPPORT=false", "ENABLE_MDNS=true", "ENABLE_REPORTING=true", "ENABLE_WEBSOCKETS=true", "ENABLE_CLIENT_CERTIFICATES=true", "INCLUDE_TRANSPORT_SECURITY_STATE_PRELOAD_LIST=true", "USE_KERBEROS=true", "USE_EXTERNAL_GSSAPI=true", "CHROME_ROOT_STORE_OPTIONAL=false", "CHROME_ROOT_STORE_ONLY=true", "CHROME_ROOT_STORE_SUPPORTED=true", "ENABLE_DEVICE_BOUND_SESSIONS=true", "ENABLE_BRACKETED_PROXY_URIS=false", "ENABLE_QUIC_PROXY_SUPPORT=false"],
    )
    chromium_python_action(
        name = "flags_c7980a6bfb47c4e4",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "net/base/cronet_buildflags.h", "--rulename", "//net:cronet_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/net/base/cronet_buildflags.h": "gen/net/base/cronet_buildflags.h"},
        response_file_contents = ["--flags", "CRONET_BUILD=false"],
    )
    chromium_python_action(
        name = "flags_19ea92f8f74461d8",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "net/disk_cache//buildflags.h", "--rulename", "//net:disk_cache_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/net/disk_cache/buildflags.h": "gen/net/disk_cache/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_DISK_CACHE_SQL_BACKEND=true"],
    )
    chromium_python_action(
        name = "flags_05355e960b5f7af8",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "pdf/buildflags.h", "--rulename", "//pdf:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/pdf/buildflags.h": "gen/pdf/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_PDF_INK2=true", "ENABLE_PDF_SAVE_TO_DRIVE=true", "ENABLE_PDF=true"],
    )
    chromium_python_action(
        name = "flags_b20ce40d0a6165f9",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "printing/buildflags/buildflags.h", "--rulename", "//printing/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/printing/buildflags/buildflags.h": "gen/printing/buildflags/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_PRINT_PREVIEW=true", "ENABLE_BASIC_PRINT_DIALOG=true", "ENABLE_CONCURRENT_BASIC_PRINT_DIALOGS=true", "ENABLE_OOP_BASIC_PRINT_DIALOG=false", "ENABLE_OOP_PRINTING_NO_OOP_BASIC_PRINT_DIALOG=true", "ENABLE_OOP_PRINTING=true", "USE_CUPS=true", "USE_CUPS_IPP=true", "ENABLE_PRINTING=true"],
    )
    chromium_python_action(
        name = "flags_20ff349c59251f12",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "rlz/buildflags/buildflags.h", "--rulename", "//rlz/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/rlz/buildflags/buildflags.h": "gen/rlz/buildflags/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_RLZ=false"],
    )
    chromium_python_action(
        name = "flags_bf89c8e2ceac3b63",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "sandbox/policy/chromecast_sandbox_allowlist_buildflags.h", "--rulename", "//sandbox/policy:chromecast_sandbox_allowlist_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/sandbox/policy/chromecast_sandbox_allowlist_buildflags.h": "gen/sandbox/policy/chromecast_sandbox_allowlist_buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_CHROMECAST_GPU_SANDBOX_ALLOWLIST=false"],
    )
    chromium_python_action(
        name = "flags_7aedc8a354b79e33",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "sandbox/sandbox_buildflags.h", "--rulename", "//sandbox:sandbox_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/sandbox/sandbox_buildflags.h": "gen/sandbox/sandbox_buildflags.h"},
        response_file_contents = ["--flags", "USE_SECCOMP_BPF=true"],
    )
    chromium_python_action(
        name = "flags_719b7206797ac8c8",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "services/accessibility/buildflags.h", "--rulename", "//services/accessibility:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/services/accessibility/buildflags.h": "gen/services/accessibility/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_ACCESSIBILITY_SERVICE=false", "SUPPORTS_OS_ACCESSIBILITY_SERVICE=false"],
    )
    chromium_python_action(
        name = "flags_7efdec36f91981d9",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "services/device/public/cpp/compute_pressure/buildflags.h", "--rulename", "//services/device/public/cpp/compute_pressure:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/services/device/public/cpp/compute_pressure/buildflags.h": "gen/services/device/public/cpp/compute_pressure/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_COMPUTE_PRESSURE=true"],
    )
    chromium_python_action(
        name = "flags_e1af6c51ee9458b7",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "services/device/public/cpp/geolocation/buildflags.h", "--rulename", "//services/device/public/cpp/geolocation:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/services/device/public/cpp/geolocation/buildflags.h": "gen/services/device/public/cpp/geolocation/buildflags.h"},
        response_file_contents = ["--flags", "OS_LEVEL_GEOLOCATION_PERMISSION_SUPPORTED=false"],
    )
    chromium_python_action(
        name = "flags_00f56ad2df52470f",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "services/network/public/cpp/network_service_buildflags.h", "--rulename", "//services/network/public/cpp:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/services/network/public/cpp/network_service_buildflags.h": "gen/services/network/public/cpp/network_service_buildflags.h"},
        response_file_contents = ["--flags", "IS_CT_SUPPORTED=true", "IS_P2P_ENABLED=true", "IS_DIRECTORY_TRANSFER_REQUIRED=false"],
    )
    chromium_python_action(
        name = "flags_093d8b2a2cb48d1c",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "services/on_device_model/public/cpp/buildflags.h", "--rulename", "//services/on_device_model/public/cpp:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/services/on_device_model/public/cpp/buildflags.h": "gen/services/on_device_model/public/cpp/buildflags.h"},
        response_file_contents = ["--flags", "USE_ON_DEVICE_MODEL_SERVICE=true", "USE_CHROMEOS_MODEL_SERVICE=false"],
    )
    chromium_python_action(
        name = "flags_b5d4fe77ffc5e6dc",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "services/on_device_model/ml_internal_buildflags.h", "--rulename", "//services/on_device_model:ml_internal_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/services/on_device_model/ml_internal_buildflags.h": "gen/services/on_device_model/ml_internal_buildflags.h"},
        response_file_contents = ["--flags", "BUILD_WITH_ML_INTERNAL=false"],
    )
    chromium_python_action(
        name = "flags_db2294db2eb92890",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "services/screen_ai/buildflags/buildflags.h", "--rulename", "//services/screen_ai/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/services/screen_ai/buildflags/buildflags.h": "gen/services/screen_ai/buildflags/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_SCREEN_AI_BROWSERTESTS=true", "ENABLE_SCREEN_AI_SERVICE=true", "USE_FAKE_SCREEN_AI=false"],
    )
    chromium_python_action(
        name = "flags_f27956ee692ccfd2",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "services/tracing/public/cpp/buildflags.h", "--rulename", "//services/tracing/public/cpp:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/services/tracing/public/cpp/buildflags.h": "gen/services/tracing/public/cpp/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_LOADER_LOCK_SAMPLING=false"],
    )
    chromium_python_action(
        name = "flags_63c39dd9480c71b4",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "services/video_effects/public/cpp/buildflags.h", "--rulename", "//services/video_effects/buildflags:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/services/video_effects/public/cpp/buildflags.h": "gen/services/video_effects/public/cpp/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_VIDEO_EFFECTS=false"],
    )
    chromium_python_action(
        name = "flags_246278f030854cc1",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "services/webnn/buildflags.h", "--rulename", "//services/webnn:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/services/webnn/buildflags.h": "gen/services/webnn/buildflags.h"},
        response_file_contents = ["--flags", "WEBNN_USE_TFLITE=true", "WEBNN_USE_CHROME_ML_API=false", "WEBNN_ENABLE_TFLITE_PROFILER=false"],
    )
    chromium_python_action(
        name = "flags_b42dd79b4b9119b6",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "skia/buildflags.h", "--rulename", "//skia:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/skia/buildflags.h": "gen/skia/buildflags.h"},
        response_file_contents = ["--flags", "SKIA_SUPPORT_SKOTTIE=true", "SKIA_USE_DAWN=true", "SKIA_USE_METAL=false"],
    )
    chromium_python_action(
        name = "flags_c75f449f3c9dd262",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "third_party/blink/public/common/buildflags.h", "--rulename", "//third_party/blink/public/common:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/third_party/blink/public/common/buildflags.h": "gen/third_party/blink/public/common/buildflags.h"},
        response_file_contents = ["--flags", "RTC_USE_H264=false", "RTC_USE_H265=false"],
    )
    chromium_python_action(
        name = "flags_e38eac1b93bf3065",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "third_party/blink/public/public_buildflags.h", "--rulename", "//third_party/blink/public:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/third_party/blink/public/public_buildflags.h": "gen/third_party/blink/public/public_buildflags.h"},
        response_file_contents = ["--flags", "USE_MINIKIN_HYPHENATION=true", "ENABLE_UNHANDLED_TAP=false"],
    )
    chromium_python_action(
        name = "flags_3381e00b08368cda",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "third_party/blink/renderer/bindings/buildflags.h", "--rulename", "//third_party/blink/renderer/bindings:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/third_party/blink/renderer/bindings/buildflags.h": "gen/third_party/blink/renderer/bindings/buildflags.h"},
        response_file_contents = ["--flags", "PRODUCE_V8_COMPILE_HINTS=true"],
    )
    chromium_python_action(
        name = "flags_a1b8d843db4e9c01",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "third_party/blink/renderer/core/animation/buildflags.h", "--rulename", "//third_party/blink/renderer/core/animation:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/third_party/blink/renderer/core/animation/buildflags.h": "gen/third_party/blink/renderer/core/animation/buildflags.h"},
        response_file_contents = ["--flags", "BLINK_ANIMATION_USE_TIME_DELTA=false"],
    )
    chromium_python_action(
        name = "flags_40fec0b5c6d3f9eb",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "third_party/blink/renderer/core/buildflags.h", "--rulename", "//third_party/blink/renderer/core:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/third_party/blink/renderer/core/buildflags.h": "gen/third_party/blink/renderer/core/buildflags.h"},
        response_file_contents = ["--flags", "TARGET_OS_IS_ANDROID=false", "USE_EXTERNAL_POPUP_MENU=false"],
    )
    chromium_python_action(
        name = "flags_7f6d893aa77527ee",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "third_party/blink/renderer/platform/heap/heap_buildflags.h", "--rulename", "//third_party/blink/renderer/platform/heap:blink_heap_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/third_party/blink/renderer/platform/heap/heap_buildflags.h": "gen/third_party/blink/renderer/platform/heap/heap_buildflags.h"},
        response_file_contents = ["--flags", "VERBOSE_PERSISTENT=false", "BLINK_HEAP_INSIDE_SHARED_LIBRARY=false"],
    )
    chromium_python_action(
        name = "flags_c28dec971a04efee",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "third_party/blink/renderer/platform/bindings/buildflags.h", "--rulename", "//third_party/blink/renderer/platform:bindings_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/third_party/blink/renderer/platform/bindings/buildflags.h": "gen/third_party/blink/renderer/platform/bindings/buildflags.h"},
        response_file_contents = ["--flags", "RCS_COUNT_EVERYTHING=false", "BLINK_BINDINGS_TRACE_ENABLED=false", "HAS_ZSTD_COMPRESSION=true"],
    )
    chromium_python_action(
        name = "flags_f57014c565fdb1f3",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "third_party/ffmpeg/ffmpeg_features.h", "--rulename", "//third_party/ffmpeg:ffmpeg_features", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/third_party/ffmpeg/ffmpeg_features.h": "gen/third_party/ffmpeg/ffmpeg_features.h"},
        response_file_contents = ["--flags", "USE_SYSTEM_FFMPEG=false"],
    )
    chromium_python_action(
        name = "flags_52b38204488b71b4",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "third_party/tflite/buildflags.h", "--rulename", "//third_party/tflite:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/third_party/tflite/buildflags.h": "gen/third_party/tflite/buildflags.h"},
        response_file_contents = ["--flags", "BUILD_TFLITE_WITH_NNAPI=false", "BUILD_TFLITE_WITH_OPENCL=false", "BUILD_TFLITE_WITH_XNNPACK=true"],
    )
    chromium_python_action(
        name = "flags_4cff0ab8b7842eb7",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "third_party/widevine/cdm/buildflags.h", "--rulename", "//third_party/widevine/cdm:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/third_party/widevine/cdm/buildflags.h": "gen/third_party/widevine/cdm/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_WIDEVINE=false", "BUNDLE_WIDEVINE_CDM=false", "ENABLE_WIDEVINE_CDM_COMPONENT=false", "ENABLE_MEDIA_FOUNDATION_WIDEVINE_CDM=false"],
    )
    chromium_python_action(
        name = "flags_a760b561adf08a42",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "tools/v8_context_snapshot/buildflags.h", "--rulename", "//tools/v8_context_snapshot:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/tools/v8_context_snapshot/buildflags.h": "gen/tools/v8_context_snapshot/buildflags.h"},
        response_file_contents = ["--flags", "USE_V8_CONTEXT_SNAPSHOT=true", "INCLUDE_BOTH_V8_SNAPSHOTS=false", "V8_CONTEXT_SNAPSHOT_FILENAME=\"v8_context_snapshot.bin\""],
    )
    chromium_python_action(
        name = "flags_4b60643b7c0d2063",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "ui/base/buildflags.h", "--rulename", "//ui/base:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/ui/base/buildflags.h": "gen/ui/base/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_HIDPI=true", "ENABLE_MESSAGE_CENTER=true", "USE_ATK=true", "USE_XKBCOMMON=true", "HAS_NATIVE_ACCESSIBILITY=true", "HAS_PLATFORM_ACCESSIBILITY_SUPPORT=true", "USE_GTK=true", "USE_QT=true", "ENABLE_PSEUDOLOCALES=true"],
    )
    chromium_python_action(
        name = "flags_ebf79c45a21c036e",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "ui/base/ozone_buildflags.h", "--rulename", "//ui/base:ozone_buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/ui/base/ozone_buildflags.h": "gen/ui/base/ozone_buildflags.h"},
        response_file_contents = ["--flags", "IS_OZONE_WAYLAND=true", "IS_OZONE_X11=true"],
    )
    chromium_python_action(
        name = "flags_bbd993ab174bf936",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "ui/gl/buildflags.h", "--rulename", "//ui/gl:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/ui/gl/buildflags.h": "gen/ui/gl/buildflags.h"},
        response_file_contents = ["--flags", "DAWN_ENABLE_BACKEND_OPENGLES=true", "ENABLE_SWIFTSHADER=true", "USE_DAWN=true", "USE_STATIC_ANGLE=false", "USE_OPENGL_APITRACE=false", "ENABLE_VALIDATING_COMMAND_DECODER=false", "ENABLE_VULKAN=true"],
    )
    chromium_python_action(
        name = "flags_d2e75749d4c021c1",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "ui/views/buildflags.h", "--rulename", "//ui/views:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/ui/views/buildflags.h": "gen/ui/views/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_DESKTOP_AURA=true", "SUPPORTS_AX_TEXT_OFFSETS=false"],
    )
    chromium_python_action(
        name = "flags_f7f446bb9062509e",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "ui/webui/buildflags.h", "--rulename", "//ui/webui:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/ui/webui/buildflags.h": "gen/ui/webui/buildflags.h"},
        response_file_contents = ["--flags", "ENABLE_WEBUI_GENERATE_CODE_CACHE=true"],
    )
    chromium_python_action(
        name = "flags_3d060ab1285571fd",
        srcs = {"//build:write_buildflag_header.py": "build/write_buildflag_header.py"},
        script = "build/write_buildflag_header.py",
        args = ["--output", "url/buildflags.h", "--rulename", "//url:buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"],
        outs = {"gen/url/buildflags.h": "gen/url/buildflags.h"},
        response_file_contents = ["--flags", "USE_PLATFORM_ICU_ALTERNATIVES=false"],
    )
    native.filegroup(
        name = name,
        srcs = [":flags_4a0fe733a7b9f6e6", ":flags_6a6faeb3837876da", ":flags_4adb3f90976138a7", ":flags_8e0709a9e3a1309d", ":flags_81151354f19f1afa", ":flags_c0d8c63cf51403c4", ":flags_3f21f430a9782828", ":flags_1253acc8a725ddc4", ":flags_58a0769af7adeddc", ":flags_4108a3a8378cd80c", ":flags_9f913a7112e3928c", ":flags_5b72dc0e3098f3e6", ":flags_368b50dddafa53d9", ":flags_43e5bf28b09ed7e9", ":flags_89020abe85087279", ":flags_79eda2c62c056f4e", ":flags_e0c2bfdeb42485bf", ":flags_3c33d3e57bf90d92", ":flags_c62c00b03a3133ce", ":flags_7f150688c68d3bd4", ":flags_0640069825305db6", ":flags_eb3aab2d26244c93", ":flags_254bdcedfad33bc7", ":flags_ec1c86a4ff0e22de", ":flags_5ac8dcfcbd0949e3", ":flags_700c9f3ea0d9460e", ":flags_e47bada76fbc9ee6", ":flags_87f66ff3811569ec", ":flags_971c9346a9306ed5", ":flags_e86b94280348bf30", ":flags_10991f8e7c2e395e", ":flags_c5256b5b57a57dfd", ":flags_e375ca1c2f3a5cc4", ":flags_0df2092a616eaabc", ":flags_aa7f27e14766b296", ":flags_bcb592b9958432a8", ":flags_9e9bee6c8484bb92", ":flags_520d9f2f121ab24e", ":flags_a3fb1f6d19e9eaa9", ":flags_763ee8bf6dcdbbbc", ":flags_a141a308871c7aea", ":flags_bac1f758d1314d23", ":flags_b0769cef119d5457", ":flags_8bc78244895640c4", ":flags_ad763c8c1d0947e2", ":flags_c07dc84e5218ae8e", ":flags_ada7700a133b8fa9", ":flags_4e963e221e3430c1", ":flags_6340ff1be00afd64", ":flags_ab6a1e461cb0bca6", ":flags_9fa1d269dba1a63c", ":flags_52458918bcf86ad2", ":flags_ffd81efe95053b99", ":flags_589c48104ee99bd4", ":flags_5b0ce081be7bc4cd", ":flags_deb476db6783e7d9", ":flags_2217c92c8e677750", ":flags_ef4b17a8f582ebc0", ":flags_aac6e5cb03eaf0be", ":flags_5163c7d9ce554144", ":flags_1e61c92b9e74f26b", ":flags_4160b12b45f69f4c", ":flags_8828c4cef7335afa", ":flags_b58bf161c4020769", ":flags_f3da8a2600443da2", ":flags_8f4b7865250bd883", ":flags_b1d6f652768b5fb7", ":flags_57ce1ae95c9f7f03", ":flags_3af9e0dfaf81948c", ":flags_d00145fd5e430d8d", ":flags_037f56cbccbc4d50", ":flags_37cc4cd31fda8bb3", ":flags_427bd7b2efd21661", ":flags_1519a75c7d61d445", ":flags_d9c9e95aefb43522", ":flags_5939b67cd19c3e20", ":flags_68d58eb2ae10d315", ":flags_6157a8233d1bc7b8", ":flags_5fcdf86d6913d966", ":flags_b46d8228bf7002c1", ":flags_fc79f1e1e84eb816", ":flags_9555339617b91e30", ":flags_91600bf120c1ff21", ":flags_c7980a6bfb47c4e4", ":flags_19ea92f8f74461d8", ":flags_05355e960b5f7af8", ":flags_b20ce40d0a6165f9", ":flags_20ff349c59251f12", ":flags_bf89c8e2ceac3b63", ":flags_7aedc8a354b79e33", ":flags_719b7206797ac8c8", ":flags_7efdec36f91981d9", ":flags_e1af6c51ee9458b7", ":flags_00f56ad2df52470f", ":flags_093d8b2a2cb48d1c", ":flags_b5d4fe77ffc5e6dc", ":flags_db2294db2eb92890", ":flags_f27956ee692ccfd2", ":flags_63c39dd9480c71b4", ":flags_246278f030854cc1", ":flags_b42dd79b4b9119b6", ":flags_c75f449f3c9dd262", ":flags_e38eac1b93bf3065", ":flags_3381e00b08368cda", ":flags_a1b8d843db4e9c01", ":flags_40fec0b5c6d3f9eb", ":flags_7f6d893aa77527ee", ":flags_c28dec971a04efee", ":flags_f57014c565fdb1f3", ":flags_52b38204488b71b4", ":flags_4cff0ab8b7842eb7", ":flags_a760b561adf08a42", ":flags_4b60643b7c0d2063", ":flags_ebf79c45a21c036e", ":flags_bbd993ab174bf936", ":flags_d2e75749d4c021c1", ":flags_f7f446bb9062509e", ":flags_3d060ab1285571fd"],
    )

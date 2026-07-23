#!/bin/sh
# Local runtime checker only. It never proves a production/fixed launch.
set -eu

fail() {
  printf '%s\n' "runtime_bootstrap_error=$1" >&2
  exit 1
}

digest() {
  /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'
}

identity() {
  /usr/bin/stat -f '%i:%z:%m:%c' "$1"
}

profile_value() {
  key=$1
  /usr/bin/awk -v key="$key" '
    { line=$0; sub(/^[[:space:]]*/, "", line); prefix="\"" key "\": \"" }
    index(line, prefix) == 1 {
      value=substr(line, length(prefix)+1); sub(/\",?[[:space:]]*$/, "", value); print value; found++
    }
    END { if (found != 1) exit 2 }
  ' docs/contracts/package.json || fail "launch profile scalar is missing or duplicated: $key"
}

verify_tool() {
  tool_path=$1 expected=$2
  [ -f "$tool_path" ] && [ ! -L "$tool_path" ] || fail "external launch tool is not a regular fixed path: $tool_path"
  [ "$(digest "$tool_path")" = "$expected" ] || fail "external launch tool identity mismatch: $tool_path"
}

[ "$#" -ge 1 ] || fail "missing Python entry path"
[ "$0" = "docs/contracts/runtime-bootstrap-v1.sh" ] || fail "bootstrap entry must use the fixed repo-relative path"
[ "$(/bin/ps -p $$ -o comm= | /usr/bin/tr -d ' ')" = "/bin/sh" ] || fail "actual shell executable mismatch"
[ "$(/bin/pwd -P)" = "$PWD" ] || fail "working directory is not physical"
[ "$(/usr/bin/uname -s)" = "Darwin" ] || fail "operating system mismatch"
[ "$(/usr/bin/uname -r)" = "25.5.0" ] || fail "operating system release mismatch"
[ "$(/usr/bin/uname -m)" = "arm64" ] || fail "architecture mismatch"
[ "$(/usr/bin/sw_vers -buildVersion)" = "25F84" ] || fail "operating system build mismatch"
[ "$(/usr/bin/shasum -a 256 /bin/sh | /usr/bin/awk '{print $1}')" = "ad5c194b05f83bc5e793c1cd67b148a4b680467b5a5730ab1a31fe4e6460ee9f" ] || fail "local /bin/sh identity mismatch"

# The initial root is the Darwin kernel/process image plus fixed /bin/sh,
# ps, shasum and awk.  All other external commands are measured from there.
verify_tool /bin/sh ad5c194b05f83bc5e793c1cd67b148a4b680467b5a5730ab1a31fe4e6460ee9f
verify_tool /bin/ps 472992c470606d28f577590decfecd7f4a20f832fd92c671bebc6d44790b5d02
verify_tool /usr/bin/shasum 0812595f981a26f813d98dc380af14d4af427626c9339eda29eb849ae13de1e3
verify_tool /usr/bin/awk 3693175058d0be720f941a8e9c645756f7d38848f3457abd938d8e27ba35f8ab
verify_tool /bin/pwd ff2c9704307a064566ae9835ff0becf3a765481580c0abe28c8654e2a3045639
verify_tool /bin/rm 0e7aa0987cecc8d8ca629e1c61857321e8e281a6c1d0711b21163a15e454dc9d
verify_tool /bin/sleep a2be9ba33f4fbf10a4f2702cd9b687ac98274ad28de509109ee86f2f4b0e2beb
verify_tool /usr/bin/env 6e506aec3c0cff703ac1e66cedc6f1945354ad41339a38db4425c7c88227128f
verify_tool /usr/bin/find cbab4ddd20b57c5090196f79b1c969e8a17fc48b4bb8e4a18765d0bbc714481e
verify_tool /usr/bin/grep 569588bf23c56895f046b63b029285217e442d46bec1b18498b58fefb50d8f1f
verify_tool /usr/bin/mktemp 7bb3299fdb41f16ea5d9f7748cb5cb654b93208e0a1d1d78360145dcbbfb21fe
verify_tool /usr/bin/otool 179301dcb41ea78accc3fa0048a7e6f6710d891945a751a34addd622020c1818
verify_tool /usr/bin/readlink 934656def5cfb8e85b2e4d983bb59ba97479cec49b63b4ea2fa42d067c569242
verify_tool /usr/bin/sort e595f29543691f7355d16035f71992512c6a23804f9447b73e6d484b7887d731
verify_tool /usr/bin/stat 934656def5cfb8e85b2e4d983bb59ba97479cec49b63b4ea2fa42d067c569242
verify_tool /usr/bin/sw_vers f4704a35bc196e6dd101a7de40f9e9ce51dd17bdba7ef29ce465a00d123f2ec5
verify_tool /usr/bin/tr 1ddc659c4c983056863cad854384c35d78d004dd2c53cc63ea3b3b380e76233a
verify_tool /usr/bin/uname c189136263d277786f29a16eb3137de7bcf4512d2282d0036f440022f325bfc4
verify_tool /usr/bin/wc 48afbe8af0942865f6ee7b5bfface7d9f3ec2b6ab71e81deb3ae47b8644b804f

for name in $(/usr/bin/env | /usr/bin/awk -F= '$1 ~ /^(DYLD_|LD_|PYTHON)/ && $1 !~ /^(PYTHONHASHSEED|PYTHONDONTWRITEBYTECODE|PYTHONUTF8)$/ {print $1}'); do
  fail "unregistered loader/Python environment: $name"
done

nofollow_relative() {
  relative=$1
  current=
  old_ifs=$IFS
  IFS=/
  for segment in $relative; do
    IFS=$old_ifs
    [ -n "$segment" ] && [ "$segment" != . ] && [ "$segment" != .. ] || fail "non-canonical repository path"
    if [ -z "$current" ]; then current=$segment; else current=$current/$segment; fi
    [ ! -L "$current" ] || fail "repository path component is a symlink: $current"
    IFS=/
  done
  IFS=$old_ifs
}

nofollow_absolute() {
  absolute=$1
  case "$absolute" in /*) ;; *) fail "runtime path is not absolute" ;; esac
  current=
  old_ifs=$IFS
  IFS=/
  for segment in $absolute; do
    IFS=$old_ifs
    [ -n "$segment" ] || { IFS=/; continue; }
    if [ -z "$current" ]; then current=/$segment; else current=$current/$segment; fi
    [ ! -L "$current" ] || fail "runtime path component is a symlink: $current"
    IFS=/
  done
  IFS=$old_ifs
}

# Freeze every repository bootstrap component before any repository Python byte
# is imported or executed.  Descriptors 5/6/7 survive exec for guard replay.
bootstrap_path=docs/contracts/runtime-bootstrap-v1.sh
profile_path=docs/contracts/package.json
guard_path=docs/contracts/python_runtime_guard_v1.py
nofollow_relative "$bootstrap_path"
nofollow_relative "$profile_path"
nofollow_relative "$guard_path"
for path in "$bootstrap_path" "$profile_path" "$guard_path"; do
  [ -f "$path" ] && [ ! -L "$path" ] || fail "launch component is not a regular no-follow file: $path"
done
bootstrap_initial=$(identity "$bootstrap_path")
profile_initial=$(identity "$profile_path")
guard_initial=$(identity "$guard_path")
exec 5< "$bootstrap_path"
exec 6< "$profile_path"
exec 7< "$guard_path"
[ "$bootstrap_initial" = "$(identity /dev/fd/5)" ] || fail "bootstrap path identity changed before open"
[ "$profile_initial" = "$(identity /dev/fd/6)" ] || fail "launch profile path identity changed before open"
[ "$guard_initial" = "$(identity /dev/fd/7)" ] || fail "runtime guard path identity changed before open"
bootstrap_sha=$(digest /dev/fd/5)
profile_sha=$(digest /dev/fd/6)
guard_sha=$(digest /dev/fd/7)
[ "$bootstrap_sha" = "$(profile_value bootstrap_raw_sha256)" ] || fail "bootstrap raw digest mismatch"
[ "$guard_sha" = "$(profile_value runtime_guard_raw_sha256)" ] || fail "runtime guard raw digest mismatch"
[ "$profile_initial" = "$(identity "$profile_path")" ] && [ "$profile_sha" = "$(digest "$profile_path")" ] || fail "launch profile changed during bootstrap"

verify_file() {
  path=$1 expected_sha=$2 expected_meta=$3
  nofollow_absolute "$path"
  [ -f "$path" ] && [ ! -L "$path" ] || fail "runtime image is not a fixed regular file: $path"
  [ "$(/usr/bin/stat -f '%u:%g:%Lp:%z' "$path")" = "$expected_meta" ] || fail "runtime image metadata mismatch: $path"
  [ "$(/usr/bin/shasum -a 256 "$path" | /usr/bin/awk '{print $1}')" = "$expected_sha" ] || fail "runtime image digest mismatch: $path"
}

python_bin=/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/bin/python3.11
stdlib_root=/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11
verify_file "$python_bin" 50de159a94723fa71090030ac642b101e27f8d29488ec4bdae91edfa1e86dbbd 501:80:755:52448
verify_file /opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/Python c12f5240b4501ea1adb52db3568c3c19f5034f1f8c665ec0c3fe2ea401b2902d 501:80:755:4883552
verify_file /opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/Resources/Python.app/Contents/MacOS/Python e17826d56c53bce1083f70b4cdb68ea29105fdc84c1c345746523f2af0b8287d 501:80:755:51392
verify_file /opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_hashlib.cpython-311-darwin.so cfde53c75126f755139658d8de1beddc4119067214ce023dafc4d9424add95a2 501:80:755:98032
verify_file /opt/homebrew/Cellar/openssl@3/3.6.2/lib/libcrypto.3.dylib ef2239cec921003b54b61968f00489271e2a2805d7d1b4e69d632423f38efe1e 501:80:444:4845712
verify_file /opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_lzma.cpython-311-darwin.so e3c5b4dc99b3bfae774a4d6e1c4bc91111dcef1b854ba4acb6da7fa71c07adf7 501:80:755:92560
verify_file /opt/homebrew/Cellar/xz/5.8.3/lib/liblzma.5.dylib 3d5bfa2f097c31463642b1daab5e662b44368bb4da368f85e412e7f9adcbaa10 501:80:444:184512
verify_file /opt/homebrew/Cellar/pandoc/3.9.0.2/bin/pandoc cf6698e4c7fd1b810b21987140da270289e4e0053278dd70015d670bb7909866 501:80:555:273136768
verify_file /opt/homebrew/Cellar/gmp/6.3.0/lib/libgmp.10.dylib 14123464af436d67ef69114810aa9e1e74de50e4097166fe8c110397b3ba6961 501:80:400:452352
verify_file /usr/local/bin/node a5ebb9adc969c8fcc486823ada530a4130b0d56edf954de7b05c280170487b1a 0:0:755:242234784

[ "$(/usr/bin/readlink /opt/homebrew/opt/openssl@3)" = "../Cellar/openssl@3/3.6.2" ] || fail "openssl opt target mismatch"
[ "$(/usr/bin/readlink /opt/homebrew/opt/gmp)" = "../Cellar/gmp/6.3.0" ] || fail "gmp opt target mismatch"
[ "$(/usr/bin/readlink /opt/homebrew/opt/xz)" = "../Cellar/xz/5.8.3" ] || fail "xz opt target mismatch"
/usr/bin/otool -L "$stdlib_root/lib-dynload/_hashlib.cpython-311-darwin.so" | /usr/bin/grep -Fq '/opt/homebrew/opt/openssl@3/lib/libcrypto.3.dylib ' || fail "_hashlib/libcrypto dependency edge mismatch"
/usr/bin/otool -L "$stdlib_root/lib-dynload/_lzma.cpython-311-darwin.so" | /usr/bin/grep -Fq '/opt/homebrew/opt/xz/lib/liblzma.5.dylib ' || fail "_lzma/liblzma dependency edge mismatch"
/usr/bin/otool -L /opt/homebrew/Cellar/pandoc/3.9.0.2/bin/pandoc | /usr/bin/grep -Fq '/opt/homebrew/opt/gmp/lib/libgmp.10.dylib ' || fail "Pandoc/GMP dependency edge mismatch"

manifest=$(/usr/bin/mktemp -t aq-python-runtime.XXXXXX)
trap '/bin/rm -f "$manifest"' EXIT HUP INT TERM
/usr/bin/find -P "$stdlib_root" \( -type f -o -type l \) ! -path '*/__pycache__/*' ! -name '*.pyc' ! -name '*.pyo' ! -path '*/site-packages/*' -print \
  | LC_ALL=C /usr/bin/sort \
  | while IFS= read -r path; do
      rel=${path#"$stdlib_root"/}
      if [ -L "$path" ]; then
        printf 'L\t%s\t%s\n' "$rel" "$(/usr/bin/readlink "$path")"
      else
        printf 'F\t%s\t%s\n' "$rel" "$(/usr/bin/shasum -a 256 "$path" | /usr/bin/awk '{print $1}')"
      fi
    done > "$manifest"
[ "$(/usr/bin/wc -l < "$manifest" | /usr/bin/tr -d ' ')" = 2487 ] || fail "Python stdlib tree count mismatch"
[ "$(/usr/bin/shasum -a 256 "$manifest" | /usr/bin/awk '{print $1}')" = 7cd4b339d6976a04f23d9894c1afdb172df8359441fef18a271e3e4f467c22ab ] || fail "Python stdlib tree digest mismatch"

entry=$1
shift
case "$entry" in
  docs/contracts/canonicalize-registry-v1.py) entry_id=projection-verifier-v1 ;;
  docs/contracts/run-release-gate-v1.py) entry_id=release-gate-v1 ;;
  docs/contracts/run-validation-mutations-v1.py) entry_id=mutation-runner-v1 ;;
  docs/contracts/validate-contracts-v1.py) entry_id=contract-validator-v1 ;;
  *) fail "entry is not in the exact launch allowlist" ;;
esac
nofollow_relative "$entry"
[ -f "$entry" ] && [ ! -L "$entry" ] || fail "Python entry is not a regular fixed-root file"
entry_initial=$(identity "$entry")
exec 8< "$entry"
exec 9< "$entry"
[ "$entry_initial" = "$(identity /dev/fd/8)" ] && [ "$entry_initial" = "$(identity /dev/fd/9)" ] \
  || fail "entry path identity changed before open"
entry_sha=$(digest /dev/fd/8)
[ "$entry_sha" = "$(digest /dev/fd/9)" ] || fail "entry opened descriptors differ"
[ "$entry_sha" = "$(profile_value "$entry")" ] || fail "entry raw digest/allowlist mismatch"
if [ "${AQ_BOOTSTRAP_MUTATION_TEST:-}" = "1" ]; then
  [ -n "${AQ_BOOTSTRAP_TEST_READY_FILE:-}" ] && [ -n "${AQ_BOOTSTRAP_TEST_CONTINUE_FILE:-}" ] \
    || fail "entry TOCTOU test barrier is incomplete"
  printf '%s\n' ready > "$AQ_BOOTSTRAP_TEST_READY_FILE"
  while [ ! -f "$AQ_BOOTSTRAP_TEST_CONTINUE_FILE" ]; do /bin/sleep 0.05; done
fi
[ "$entry_initial" = "$(identity "$entry")" ] && [ "$entry_sha" = "$(digest "$entry")" ] || fail "entry path changed after open"
[ "$profile_initial" = "$(identity "$profile_path")" ] && [ "$profile_sha" = "$(digest "$profile_path")" ] || fail "launch profile changed during entry binding"

runtime_identity=$(
  "$python_bin" -I -S -c 'import json,os,platform,sys,sysconfig; print(json.dumps({"abi":sysconfig.get_config_var("SOABI"),"implementation":platform.python_implementation(),"platform":sysconfig.get_platform(),"real_executable":os.path.realpath(sys.executable),"version":platform.python_version()},sort_keys=True,separators=(",",":")))'
)
expected_identity='{"abi":"cpython-311-darwin","implementation":"CPython","platform":"macosx-26.0-arm64","real_executable":"/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/bin/python3.11","version":"3.11.15"}'
[ "$runtime_identity" = "$expected_identity" ] || fail "Python implementation/version/ABI/platform identity mismatch"

printf '%s\n' 'local_runtime_checker=preflight-verified'
printf '%s\n' 'external_launch_attestation=absent'
printf '%s\n' 'launch_authority=local-audit-evidence-only-not-fixed-launch-proof'

home_value=${HOME:-/tmp}
exec /usr/bin/env -i \
  PATH=/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin \
  HOME="$home_value" LANG=C LC_ALL=C \
  PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 \
  ${AQ_VALIDATION_MUTATION_TEST:+AQ_VALIDATION_MUTATION_TEST=$AQ_VALIDATION_MUTATION_TEST} \
  ${AQ_VALIDATION_TEST_PAUSE_BEFORE_FINAL_VERIFY_MS:+AQ_VALIDATION_TEST_PAUSE_BEFORE_FINAL_VERIFY_MS=$AQ_VALIDATION_TEST_PAUSE_BEFORE_FINAL_VERIFY_MS} \
  ${AQ_VALIDATION_TEST_READY_FD:+AQ_VALIDATION_TEST_READY_FD=$AQ_VALIDATION_TEST_READY_FD} \
  ${AQ_VALIDATION_NPM_PACKAGE_ROOT:+AQ_VALIDATION_NPM_PACKAGE_ROOT=$AQ_VALIDATION_NPM_PACKAGE_ROOT} \
  ${AQ_RELEASE_GATE_MUTATION_TEST:+AQ_RELEASE_GATE_MUTATION_TEST=$AQ_RELEASE_GATE_MUTATION_TEST} \
  ${AQ_RELEASE_GATE_TEST_PAUSE_BEFORE_FINAL_VERIFY_MS:+AQ_RELEASE_GATE_TEST_PAUSE_BEFORE_FINAL_VERIFY_MS=$AQ_RELEASE_GATE_TEST_PAUSE_BEFORE_FINAL_VERIFY_MS} \
  ${AQ_RELEASE_GATE_TEST_READY_FD:+AQ_RELEASE_GATE_TEST_READY_FD=$AQ_RELEASE_GATE_TEST_READY_FD} \
  ${AQ_RELEASE_GATE_EVIDENCE:+AQ_RELEASE_GATE_EVIDENCE=$AQ_RELEASE_GATE_EVIDENCE} \
  ${AQ_MUTATION_RECIPE_SELF_TEST:+AQ_MUTATION_RECIPE_SELF_TEST=$AQ_MUTATION_RECIPE_SELF_TEST} \
  "$python_bin" -I -B -c '
import builtins,os,sys,types
def fd_bytes(number): return os.pread(number,os.fstat(number).st_size,0)
guard_path="docs/contracts/python_runtime_guard_v1.py"
guard=types.ModuleType("python_runtime_guard_v1"); guard.__file__=guard_path; sys.modules[guard.__name__]=guard
exec(compile(fd_bytes(7),guard_path,"exec"),guard.__dict__)
guard.verify_runtime(require_external_bootstrap=True)
entry=sys.argv[1]; sys.argv=sys.argv[1:]
sys.path.insert(0,"docs/contracts")
namespace={"__name__":"__main__","__file__":entry,"__package__":None,"__spec__":None,"__builtins__":builtins.__dict__}
exec(compile(fd_bytes(9),entry,"exec"),namespace)
' "$entry" "$@"

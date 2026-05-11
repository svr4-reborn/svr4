#!/usr/bin/bash

# Run all the tests under /usr/share/mlibc-tests and print the results.
# Uses bash and the timeout command to stop stuck tests.
# Set MLIBC_TEST_TIMEOUT to override the default per-test timeout.

set -e

test_dir=${1:-/usr/share/mlibc-tests}
test_timeout=${MLIBC_TEST_TIMEOUT:-30s}
total=0
passed=0
failed=0
timed_out=0

if ! command -v timeout >/dev/null 2>&1; then
	printf 'error: timeout command not found in PATH\n' >&2
	exit 1
fi

if [[ ! -d ${test_dir} ]]; then
	printf 'error: test directory not found: %s\n' "${test_dir}" >&2
	exit 1
fi

shopt -s nullglob

for test_path in "${test_dir}"/*; do
	if [[ ! -f ${test_path} || ! -x ${test_path} ]]; then
		continue
	fi

	test_name=${test_path##*/}
	total=$((total + 1))

	printf '==> %s\n' "${test_name}"

	if timeout "${test_timeout}" "${test_path}"; then
		passed=$((passed + 1))
		printf 'PASS %s\n\n' "${test_name}"
	else
		test_status=$?
		failed=$((failed + 1))
		if (( test_status == 124 )); then
			timed_out=$((timed_out + 1))
			printf 'TIMEOUT %s\n\n' "${test_name}"
		else
			printf 'FAIL %s\n\n' "${test_name}"
		fi
	fi
done

if (( total == 0 )); then
	printf 'error: no executable tests found in %s\n' "${test_dir}" >&2
	exit 1
fi

printf 'Summary: %d total, %d passed, %d failed (%d timed out)\n' \
	"${total}" "${passed}" "${failed}" "${timed_out}"

if (( failed != 0 )); then
	exit 1
fi

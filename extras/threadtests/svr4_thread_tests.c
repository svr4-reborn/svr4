#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))

#ifndef SYS_thread_create
#define SYS_thread_create 145
#define SYS_thread_exit 146
#define SYS_thread_self 147
#define SYS_futex_wait 148
#define SYS_futex_wake 149
#endif

#define TEST_TIMEOUT_SECONDS 20

struct test_case {
	const char *name;
	int (*func)(void);
	int xfail;
};

static int fail(const char *message)
{
	fprintf(stderr, "    %s\n", message);
	return 1;
}

static int fail_errno(const char *message, int error)
{
	fprintf(stderr, "    %s: %s (%d)\n", message, strerror(error), error);
	return 1;
}

#define CHECK(condition, message) \
	do { \
		if (!(condition)) \
			return fail(message); \
	} while (0)

#define CHECK_ERR(actual, expected, message) \
	do { \
		if ((actual) != (expected)) \
			return fail_errno(message, (actual)); \
	} while (0)

static long raw_syscall(long number, long arg1, long arg2, long arg3, long arg4,
    long arg5)
{
	extern uint64_t test_syscall5(long, long, long, long, long, long);
	uint64_t state;
	long value;

	errno = 0;
	state = test_syscall5(number, arg1, arg2, arg3, arg4, arg5);
	value = (long)(int32_t)state;
	if (state >> 32) {
		errno = value;
		return -1;
	}
	return value;
}

static int wait_until_eq(volatile int *value, int expected, int timeout_ms)
{
	int elapsed;

	for (elapsed = 0; elapsed < timeout_ms; elapsed += 10) {
		if (__atomic_load_n(value, __ATOMIC_ACQUIRE) == expected)
			return 0;
		usleep(10000);
	}
	return ETIMEDOUT;
}

static int test_raw_syscall_errors(void)
{
	int word;
	struct timespec zero_timeout;
	long ret;

	ret = raw_syscall(SYS_thread_self, 0, 0, 0, 0, 0);
	CHECK(ret > 0, "thread_self returned a non-positive tid");

	ret = raw_syscall(SYS_thread_create, 0, 0, 0, 0, 0);
	CHECK(ret == -1 && errno == EINVAL, "invalid thread create did not return EINVAL");

	ret = raw_syscall(SYS_futex_wait, 0, 0, 0, 0, 0);
	CHECK(ret == -1 && errno == EINVAL, "futex wait on NULL did not return EINVAL");

	ret = raw_syscall(SYS_futex_wake, 0, 0, 0, 0, 0);
	CHECK(ret == -1 && errno == EINVAL, "futex wake on NULL did not return EINVAL");

	word = 7;
	ret = raw_syscall(SYS_futex_wait, (long)&word, 0, 0, 0, 0);
	CHECK(ret == -1 && errno == EAGAIN, "futex wait mismatch did not return EAGAIN");

	zero_timeout.tv_sec = 0;
	zero_timeout.tv_nsec = 1;
	word = 0;
	ret = raw_syscall(SYS_futex_wait, (long)&word, 0, (long)&zero_timeout, 0, 0);
	CHECK(ret == -1 && errno == ETIMEDOUT, "short futex wait did not time out");

	ret = raw_syscall(SYS_futex_wake, (long)&word, 1, 0, 0, 0);
	CHECK(ret == 0, "futex wake with no waiters did not return zero");

	return 0;
}

static volatile int raw_futex_word;
static volatile int raw_futex_ready;
static volatile int raw_futex_done;

static void *raw_futex_waiter(void *arg)
{
	(void)arg;
	__atomic_add_fetch(&raw_futex_ready, 1, __ATOMIC_RELEASE);
	(void)raw_syscall(SYS_futex_wait, (long)&raw_futex_word, 0, 0, 0, 0);
	__atomic_add_fetch(&raw_futex_done, 1, __ATOMIC_RELEASE);
	return NULL;
}

static int test_raw_futex_wake_one_all(void)
{
	pthread_t threads[3];
	long ret;
	int i;

	raw_futex_word = 0;
	raw_futex_ready = 0;
	raw_futex_done = 0;

	for (i = 0; i < 3; i++)
		CHECK_ERR(pthread_create(&threads[i], NULL, raw_futex_waiter, NULL), 0,
		    "pthread_create(raw futex waiter) failed");

	CHECK_ERR(wait_until_eq(&raw_futex_ready, 3, 2000), 0,
	    "raw futex waiters did not start");
	usleep(200000);

	ret = raw_syscall(SYS_futex_wake, (long)&raw_futex_word, 0, 0, 0, 0);
	CHECK(ret == 1, "futex wake-one did not report exactly one wakeup");
	CHECK_ERR(wait_until_eq(&raw_futex_done, 1, 2000), 0,
	    "futex wake-one did not release one waiter");

	__atomic_store_n(&raw_futex_word, 1, __ATOMIC_RELEASE);
	ret = raw_syscall(SYS_futex_wake, (long)&raw_futex_word, 1, 0, 0, 0);
	CHECK(ret >= 2, "futex wake-all did not report the remaining waiters");
	CHECK_ERR(wait_until_eq(&raw_futex_done, 3, 2000), 0,
	    "futex wake-all did not release all waiters");

	for (i = 0; i < 3; i++)
		CHECK_ERR(pthread_join(threads[i], NULL), 0, "pthread_join(raw futex waiter) failed");

	return 0;
}

static void *return_worker(void *arg)
{
	int *value = arg;
	*value = 42;
	return (void *)(uintptr_t)1234;
}

static int test_create_join_return(void)
{
	pthread_t thread;
	void *result;
	int value = 0;

	CHECK_ERR(pthread_create(&thread, NULL, return_worker, &value), 0,
	    "pthread_create failed");
	CHECK_ERR(pthread_join(thread, &result), 0, "pthread_join failed");
	CHECK(value == 42, "joined thread did not update shared memory");
	CHECK((uintptr_t)result == 1234, "pthread_join returned the wrong value");
	return 0;
}

static long tid_values[5];

static void *tid_worker(void *arg)
{
	int index = (int)(uintptr_t)arg;
	tid_values[index] = raw_syscall(SYS_thread_self, 0, 0, 0, 0, 0);
	return NULL;
}

static int test_thread_ids_unique(void)
{
	pthread_t threads[4];
	int i, j;

	tid_values[0] = raw_syscall(SYS_thread_self, 0, 0, 0, 0, 0);
	CHECK(tid_values[0] > 0, "main thread tid is invalid");

	for (i = 0; i < 4; i++)
		CHECK_ERR(pthread_create(&threads[i], NULL, tid_worker, (void *)(uintptr_t)(i + 1)),
		    0, "pthread_create(tid worker) failed");
	for (i = 0; i < 4; i++)
		CHECK_ERR(pthread_join(threads[i], NULL), 0, "pthread_join(tid worker) failed");

	for (i = 0; i < 5; i++) {
		CHECK(tid_values[i] > 0, "thread tid is invalid");
		for (j = i + 1; j < 5; j++)
			CHECK(tid_values[i] != tid_values[j], "two live threads received the same tid");
	}
	return 0;
}

static pthread_mutex_t counter_mutex = PTHREAD_MUTEX_INITIALIZER;
static int shared_counter;

static void *counter_worker(void *arg)
{
	int loops = (int)(uintptr_t)arg;
	int i;

	for (i = 0; i < loops; i++) {
		pthread_mutex_lock(&counter_mutex);
		shared_counter++;
		pthread_mutex_unlock(&counter_mutex);
	}
	return NULL;
}

static int test_many_thread_mutex_counter(void)
{
	pthread_t threads[16];
	int i;

	shared_counter = 0;
	for (i = 0; i < 16; i++)
		CHECK_ERR(pthread_create(&threads[i], NULL, counter_worker, (void *)(uintptr_t)1000),
		    0, "pthread_create(counter worker) failed");
	for (i = 0; i < 16; i++)
		CHECK_ERR(pthread_join(threads[i], NULL), 0, "pthread_join(counter worker) failed");
	CHECK(shared_counter == 16000, "mutex-protected counter has the wrong value");
	return 0;
}

static __thread int tls_value;
static int tls_results[8];

static void *tls_worker(void *arg)
{
	int index = (int)(uintptr_t)arg;
	tls_value = 1000 + index;
	usleep(10000);
	tls_results[index] = tls_value;
	return NULL;
}

static int test_tls_isolation(void)
{
	pthread_t threads[8];
	int i;

	tls_value = 77;
	memset(tls_results, 0, sizeof(tls_results));
	for (i = 0; i < 8; i++)
		CHECK_ERR(pthread_create(&threads[i], NULL, tls_worker, (void *)(uintptr_t)i),
		    0, "pthread_create(tls worker) failed");
	for (i = 0; i < 8; i++)
		CHECK_ERR(pthread_join(threads[i], NULL), 0, "pthread_join(tls worker) failed");
	CHECK(tls_value == 77, "main thread TLS value was clobbered");
	for (i = 0; i < 8; i++)
		CHECK(tls_results[i] == 1000 + i, "worker TLS value was not isolated");
	return 0;
}

static pthread_once_t once_control = PTHREAD_ONCE_INIT;
static int once_count;

static void once_function(void)
{
	__atomic_add_fetch(&once_count, 1, __ATOMIC_RELAXED);
}

static void *once_worker(void *arg)
{
	(void)arg;
	if (pthread_once(&once_control, once_function))
		return (void *)1;
	return NULL;
}

static int test_pthread_once_many_threads(void)
{
	pthread_t threads[16];
	int i;

	once_control = (pthread_once_t)PTHREAD_ONCE_INIT;
	once_count = 0;
	for (i = 0; i < 16; i++)
		CHECK_ERR(pthread_create(&threads[i], NULL, once_worker, NULL), 0,
		    "pthread_create(once worker) failed");
	for (i = 0; i < 16; i++) {
		void *result;
		CHECK_ERR(pthread_join(threads[i], &result), 0, "pthread_join(once worker) failed");
		CHECK(result == NULL, "pthread_once worker failed");
	}
	CHECK(once_count == 1, "pthread_once function ran more than once");
	return 0;
}

static pthread_barrier_t barrier;
static volatile int barrier_before;
static volatile int barrier_after;

static void *barrier_worker(void *arg)
{
	int error;

	(void)arg;
	__atomic_add_fetch(&barrier_before, 1, __ATOMIC_RELEASE);
	error = pthread_barrier_wait(&barrier);
	if (error && error != PTHREAD_BARRIER_SERIAL_THREAD)
		return (void *)1;
	__atomic_add_fetch(&barrier_after, 1, __ATOMIC_RELEASE);
	return NULL;
}

static int test_barrier_release(void)
{
	pthread_t threads[6];
	int i;

	barrier_before = 0;
	barrier_after = 0;
	CHECK_ERR(pthread_barrier_init(&barrier, NULL, 7), 0, "pthread_barrier_init failed");
	for (i = 0; i < 6; i++)
		CHECK_ERR(pthread_create(&threads[i], NULL, barrier_worker, NULL), 0,
		    "pthread_create(barrier worker) failed");
	CHECK_ERR(wait_until_eq(&barrier_before, 6, 2000), 0, "barrier workers did not arrive");
	CHECK(barrier_after == 0, "barrier released before the final participant arrived");
	{
		int error = pthread_barrier_wait(&barrier);
		CHECK(error == 0 || error == PTHREAD_BARRIER_SERIAL_THREAD,
		    "main pthread_barrier_wait failed");
	}
	for (i = 0; i < 6; i++) {
		void *result;
		CHECK_ERR(pthread_join(threads[i], &result), 0, "pthread_join(barrier worker) failed");
		CHECK(result == NULL, "barrier worker failed");
	}
	CHECK(barrier_after == 6, "barrier did not release every waiter");
	CHECK_ERR(pthread_barrier_destroy(&barrier), 0, "pthread_barrier_destroy failed");
	return 0;
}

static pthread_mutex_t cond_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cond = PTHREAD_COND_INITIALIZER;
static int cond_ready;
static int cond_generation;
static int cond_woke;

static void *cond_waiter(void *arg)
{
	int target = (int)(uintptr_t)arg;

	pthread_mutex_lock(&cond_mutex);
	cond_ready++;
	while (cond_generation < target)
		pthread_cond_wait(&cond, &cond_mutex);
	cond_woke++;
	pthread_mutex_unlock(&cond_mutex);
	return NULL;
}

static int test_cond_signal_broadcast(void)
{
	pthread_t threads[3];
	int i;

	cond_ready = 0;
	cond_generation = 0;
	cond_woke = 0;
	for (i = 0; i < 3; i++)
		CHECK_ERR(pthread_create(&threads[i], NULL, cond_waiter, (void *)(uintptr_t)1), 0,
		    "pthread_create(cond waiter) failed");
	CHECK_ERR(wait_until_eq((volatile int *)&cond_ready, 3, 2000), 0,
	    "condition waiters did not start");

	pthread_mutex_lock(&cond_mutex);
	cond_generation = 1;
	CHECK_ERR(pthread_cond_signal(&cond), 0, "pthread_cond_signal failed");
	pthread_mutex_unlock(&cond_mutex);
	CHECK_ERR(wait_until_eq((volatile int *)&cond_woke, 1, 2000), 0,
	    "pthread_cond_signal did not wake one waiter");

	CHECK_ERR(pthread_cond_broadcast(&cond), 0, "pthread_cond_broadcast failed");
	for (i = 0; i < 3; i++)
		CHECK_ERR(pthread_join(threads[i], NULL), 0, "pthread_join(cond waiter) failed");
	CHECK(cond_woke == 3, "pthread_cond_broadcast did not wake the remaining waiters");
	return 0;
}

static int test_mutex_kinds(void)
{
	pthread_mutex_t mutex;
	pthread_mutexattr_t attr;

	CHECK_ERR(pthread_mutexattr_init(&attr), 0, "pthread_mutexattr_init failed");
	CHECK_ERR(pthread_mutexattr_settype(&attr, PTHREAD_MUTEX_ERRORCHECK), 0,
	    "pthread_mutexattr_settype(errorcheck) failed");
	CHECK_ERR(pthread_mutex_init(&mutex, &attr), 0, "pthread_mutex_init(errorcheck) failed");
	CHECK_ERR(pthread_mutex_lock(&mutex), 0, "pthread_mutex_lock(errorcheck) failed");
	CHECK_ERR(pthread_mutex_trylock(&mutex), EBUSY, "pthread_mutex_trylock(errorcheck) wrong result");
	CHECK_ERR(pthread_mutex_lock(&mutex), EDEADLK, "pthread_mutex_lock(errorcheck) wrong result");
	CHECK_ERR(pthread_mutex_unlock(&mutex), 0, "pthread_mutex_unlock(errorcheck) failed");
	CHECK_ERR(pthread_mutex_destroy(&mutex), 0, "pthread_mutex_destroy(errorcheck) failed");

	CHECK_ERR(pthread_mutexattr_settype(&attr, PTHREAD_MUTEX_RECURSIVE), 0,
	    "pthread_mutexattr_settype(recursive) failed");
	CHECK_ERR(pthread_mutex_init(&mutex, &attr), 0, "pthread_mutex_init(recursive) failed");
	CHECK_ERR(pthread_mutex_lock(&mutex), 0, "pthread_mutex_lock(recursive 1) failed");
	CHECK_ERR(pthread_mutex_lock(&mutex), 0, "pthread_mutex_lock(recursive 2) failed");
	CHECK_ERR(pthread_mutex_unlock(&mutex), 0, "pthread_mutex_unlock(recursive 1) failed");
	CHECK_ERR(pthread_mutex_unlock(&mutex), 0, "pthread_mutex_unlock(recursive 2) failed");
	CHECK_ERR(pthread_mutex_destroy(&mutex), 0, "pthread_mutex_destroy(recursive) failed");
	CHECK_ERR(pthread_mutexattr_destroy(&attr), 0, "pthread_mutexattr_destroy failed");
	return 0;
}

static int test_rwlock_basic_and_timed(void)
{
	pthread_rwlock_t lock;
	struct timespec deadline;
	int error;

	CHECK_ERR(pthread_rwlock_init(&lock, NULL), 0, "pthread_rwlock_init failed");
	CHECK_ERR(pthread_rwlock_rdlock(&lock), 0, "pthread_rwlock_rdlock 1 failed");
	CHECK_ERR(pthread_rwlock_rdlock(&lock), 0, "pthread_rwlock_rdlock 2 failed");
	CHECK_ERR(pthread_rwlock_trywrlock(&lock), EBUSY, "pthread_rwlock_trywrlock wrong result");
	CHECK_ERR(pthread_rwlock_unlock(&lock), 0, "pthread_rwlock_unlock read 1 failed");
	CHECK_ERR(pthread_rwlock_unlock(&lock), 0, "pthread_rwlock_unlock read 2 failed");

	CHECK_ERR(pthread_rwlock_wrlock(&lock), 0, "pthread_rwlock_wrlock failed");
	CHECK_ERR(pthread_rwlock_tryrdlock(&lock), EBUSY, "pthread_rwlock_tryrdlock wrong result");
	CHECK_ERR(clock_gettime(CLOCK_REALTIME, &deadline), 0, "clock_gettime failed");
	deadline.tv_nsec += 1000000;
	if (deadline.tv_nsec >= 1000000000L) {
		deadline.tv_nsec -= 1000000000L;
		deadline.tv_sec++;
	}
	error = pthread_rwlock_timedrdlock(&lock, &deadline);
	CHECK_ERR(error, ETIMEDOUT, "pthread_rwlock_timedrdlock wrong result");
	CHECK_ERR(pthread_rwlock_unlock(&lock), 0, "pthread_rwlock_unlock write failed");
	CHECK_ERR(pthread_rwlock_destroy(&lock), 0, "pthread_rwlock_destroy failed");
	return 0;
}

static void *detached_worker(void *arg)
{
	volatile int *done = arg;
	__atomic_store_n(done, 1, __ATOMIC_RELEASE);
	return NULL;
}

static int test_detached_thread(void)
{
	pthread_attr_t attr;
	pthread_t thread;
	volatile int done = 0;

	CHECK_ERR(pthread_attr_init(&attr), 0, "pthread_attr_init failed");
	CHECK_ERR(pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED), 0,
	    "pthread_attr_setdetachstate failed");
	CHECK_ERR(pthread_create(&thread, &attr, detached_worker, (void *)&done), 0,
	    "pthread_create(detached) failed");
	CHECK_ERR(pthread_attr_destroy(&attr), 0, "pthread_attr_destroy failed");
	CHECK_ERR(wait_until_eq(&done, 1, 2000), 0, "detached thread did not run");
	return 0;
}

static void *sleep_forever_worker(void *arg)
{
	(void)arg;
	for (;;)
		usleep(100000);
	return NULL;
}

static int test_process_exit_with_live_thread(void)
{
	pid_t pid;
	int status;

	pid = fork();
	CHECK(pid >= 0, "fork failed");
	if (pid == 0) {
		pthread_t thread;
		(void)pthread_create(&thread, NULL, sleep_forever_worker, NULL);
		usleep(100000);
		_exit(17);
	}
	CHECK(waitpid(pid, &status, 0) == pid, "waitpid failed");
	CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 17,
	    "process exit with live thread returned the wrong status");
	return 0;
}

static int test_process_abort_with_live_thread(void)
{
	pid_t pid;
	int status;

	pid = fork();
	CHECK(pid >= 0, "fork failed");
	if (pid == 0) {
		pthread_t thread;
		(void)pthread_create(&thread, NULL, sleep_forever_worker, NULL);
		usleep(100000);
		abort();
	}
	CHECK(waitpid(pid, &status, 0) == pid, "waitpid failed");
	CHECK(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT,
	    "process abort with live thread returned the wrong status");
	return 0;
}

static void *exit_from_worker(void *arg)
{
	(void)arg;
	exit(23);
}

static int test_thread_exit_is_process_wide(void)
{
	pid_t pid;
	int status;

	pid = fork();
	CHECK(pid >= 0, "fork failed");
	if (pid == 0) {
		pthread_t thread;
		(void)pthread_create(&thread, NULL, exit_from_worker, NULL);
		sleep(5);
		_exit(99);
	}
	CHECK(waitpid(pid, &status, 0) == pid, "waitpid failed");
	CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 23,
	    "exit() from a worker thread did not terminate the process");
	return 0;
}

static pthread_mutex_t timed_mutex;
static volatile int timed_mutex_ready;

static void *timed_mutex_holder(void *arg)
{
	(void)arg;
	pthread_mutex_lock(&timed_mutex);
	__atomic_store_n(&timed_mutex_ready, 1, __ATOMIC_RELEASE);
	usleep(1000000);
	pthread_mutex_unlock(&timed_mutex);
	return NULL;
}

static int test_timed_mutex_timeout(void)
{
	pthread_t thread;
	struct timespec deadline;
	int error;

	timed_mutex_ready = 0;
	CHECK_ERR(pthread_mutex_init(&timed_mutex, NULL), 0, "pthread_mutex_init failed");
	CHECK_ERR(pthread_create(&thread, NULL, timed_mutex_holder, NULL), 0,
	    "pthread_create(timed mutex holder) failed");
	CHECK_ERR(wait_until_eq(&timed_mutex_ready, 1, 2000), 0,
	    "timed mutex holder did not lock the mutex");
	CHECK_ERR(clock_gettime(CLOCK_REALTIME, &deadline), 0, "clock_gettime failed");
	deadline.tv_nsec += 100000000;
	if (deadline.tv_nsec >= 1000000000L) {
		deadline.tv_nsec -= 1000000000L;
		deadline.tv_sec++;
	}
	error = pthread_mutex_timedlock(&timed_mutex, &deadline);
	CHECK_ERR(error, ETIMEDOUT, "pthread_mutex_timedlock wrong result");
	CHECK_ERR(pthread_join(thread, NULL), 0, "pthread_join(timed mutex holder) failed");
	CHECK_ERR(pthread_mutex_destroy(&timed_mutex), 0, "pthread_mutex_destroy failed");
	return 0;
}

static int test_timed_cond_past_timeout(void)
{
	pthread_condattr_t attr;
	pthread_cond_t local_cond;
	pthread_mutex_t mutex;
	struct timespec deadline;
	int error;

	CHECK_ERR(pthread_condattr_init(&attr), 0, "pthread_condattr_init failed");
	CHECK_ERR(pthread_condattr_setclock(&attr, CLOCK_MONOTONIC), 0,
	    "pthread_condattr_setclock failed");
	CHECK_ERR(pthread_cond_init(&local_cond, &attr), 0, "pthread_cond_init failed");
	CHECK_ERR(pthread_mutex_init(&mutex, NULL), 0, "pthread_mutex_init failed");
	CHECK_ERR(clock_gettime(CLOCK_MONOTONIC, &deadline), 0, "clock_gettime failed");
	deadline.tv_nsec -= 1000000;
	if (deadline.tv_nsec < 0) {
		deadline.tv_nsec += 1000000000L;
		deadline.tv_sec--;
	}
	CHECK_ERR(pthread_mutex_lock(&mutex), 0, "pthread_mutex_lock failed");
	error = pthread_cond_timedwait(&local_cond, &mutex, &deadline);
	CHECK_ERR(error, ETIMEDOUT, "pthread_cond_timedwait with past deadline wrong result");
	CHECK_ERR(pthread_mutex_unlock(&mutex), 0, "pthread_mutex_unlock failed");
	CHECK_ERR(pthread_mutex_destroy(&mutex), 0, "pthread_mutex_destroy failed");
	CHECK_ERR(pthread_cond_destroy(&local_cond), 0, "pthread_cond_destroy failed");
	CHECK_ERR(pthread_condattr_destroy(&attr), 0, "pthread_condattr_destroy failed");
	return 0;
}

static const struct test_case tests[] = {
	{ "raw_syscall_errors", test_raw_syscall_errors, 0 },
	{ "raw_futex_wake_one_all", test_raw_futex_wake_one_all, 0 },
	{ "create_join_return", test_create_join_return, 0 },
	{ "thread_ids_unique", test_thread_ids_unique, 0 },
	{ "many_thread_mutex_counter", test_many_thread_mutex_counter, 0 },
	{ "tls_isolation", test_tls_isolation, 0 },
	{ "pthread_once_many_threads", test_pthread_once_many_threads, 0 },
	{ "barrier_release", test_barrier_release, 0 },
	{ "cond_signal_broadcast", test_cond_signal_broadcast, 0 },
	{ "mutex_kinds", test_mutex_kinds, 0 },
	{ "rwlock_basic_and_timed", test_rwlock_basic_and_timed, 0 },
	{ "detached_thread", test_detached_thread, 0 },
	{ "process_exit_with_live_thread", test_process_exit_with_live_thread, 0 },
	{ "process_abort_with_live_thread", test_process_abort_with_live_thread, 0 },
	{ "thread_exit_is_process_wide", test_thread_exit_is_process_wide, 1 },
	{ "timed_mutex_timeout", test_timed_mutex_timeout, 1 },
	{ "timed_cond_past_timeout", test_timed_cond_past_timeout, 0 },
};

static int name_matches(const char *name, const char *filter)
{
	return filter == NULL || strstr(name, filter) != NULL;
}

static int run_test(const struct test_case *test, int strict)
{
	pid_t pid;
	int status;

	printf("[ RUN      ] %s%s\n", test->name, test->xfail && !strict ? " (xfail)" : "");
	fflush(stdout);

	pid = fork();
	if (pid < 0) {
		printf("[ FAIL     ] %s: fork failed: %s\n", test->name, strerror(errno));
		return 1;
	}

	if (pid == 0) {
		alarm(TEST_TIMEOUT_SECONDS);
		_exit(test->func() ? 1 : 0);
	}

	if (waitpid(pid, &status, 0) != pid) {
		printf("[ FAIL     ] %s: waitpid failed: %s\n", test->name, strerror(errno));
		return 1;
	}

	if (WIFEXITED(status) && WEXITSTATUS(status) == 0) {
		if (test->xfail && !strict)
			printf("[ XPASS    ] %s\n", test->name);
		else
			printf("[       OK ] %s\n", test->name);
		return 0;
	}

	if (test->xfail && !strict) {
		printf("[ XFAIL    ] %s\n", test->name);
		return 0;
	}

	if (WIFSIGNALED(status))
		printf("[ FAIL     ] %s: signal %d\n", test->name, WTERMSIG(status));
	else
		printf("[ FAIL     ] %s: exit %d\n", test->name, WEXITSTATUS(status));
	return 1;
}

int main(int argc, char **argv)
{
	const char *filter = NULL;
	int strict = 0;
	int failures = 0;
	int selected = 0;
	int i;

	setvbuf(stdout, NULL, _IONBF, 0);
	setvbuf(stderr, NULL, _IONBF, 0);

	for (i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--strict")) {
			strict = 1;
		} else if (!strcmp(argv[i], "--list")) {
			int j;
			for (j = 0; j < (int)ARRAY_SIZE(tests); j++)
				printf("%s%s\n", tests[j].name, tests[j].xfail ? " xfail" : "");
			return 0;
		} else if (!strcmp(argv[i], "--only") && i + 1 < argc) {
			filter = argv[++i];
		} else {
			fprintf(stderr, "usage: %s [--strict] [--list] [--only substring]\n", argv[0]);
			return 2;
		}
	}

	for (i = 0; i < (int)ARRAY_SIZE(tests); i++) {
		if (!name_matches(tests[i].name, filter))
			continue;
		selected++;
		failures += run_test(&tests[i], strict);
	}

	if (!selected) {
		fprintf(stderr, "no tests matched\n");
		return 2;
	}

	printf("[ SUMMARY  ] selected=%d failures=%d mode=%s\n",
	    selected, failures, strict ? "strict" : "normal");
	return failures ? 1 : 0;
}
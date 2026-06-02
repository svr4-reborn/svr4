project('svr4_threadtests', 'c', default_options : ['c_std=gnu11'])

executable('svr4-thread-tests', 'svr4_thread_tests.c', 'raw_syscall.S',
    install : true,
    install_dir : '/usr/bin')

install_data('run-svr4-thread-tests', install_dir : '/usr/bin')